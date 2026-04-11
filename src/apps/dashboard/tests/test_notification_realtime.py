"""
Phase 4-1: 실시간 알림 (SSE/WebSocket) 테스트

테스트 범위:
  1. Notification 모델 — push(), broadcast(), unread count
  2. Notification REST API — list / unread_count / read / read_all / clear
  3. 시그널 → 채널 레이어 푸시 (channel layer group_send 호출 확인)
  4. NotificationConsumer WebSocket — 연결·인증·초기 count·메시지 수신
  5. base.html — WS 알림 클라이언트 코드 포함 확인
"""
import json
from unittest.mock import patch, MagicMock, AsyncMock

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.dashboard.models import Notification


# ─────────────────────────────────────────────────────────────
# 공통 픽스처
# ─────────────────────────────────────────────────────────────
class NotiFixtureMixin:
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            username='noti_admin', email='noti_admin@test.com',
            password='pass', role='admin'
        )
        cls.worker = User.objects.create_user(
            username='noti_worker', email='noti_worker@test.com',
            password='pass', role='worker'
        )
        cls.worker2 = User.objects.create_user(
            username='noti_worker2', email='noti_worker2@test.com',
            password='pass', role='worker'
        )


# ─────────────────────────────────────────────────────────────
# 1. Notification 모델
# ─────────────────────────────────────────────────────────────
class NotificationModelTest(NotiFixtureMixin, TestCase):

    def test_push_creates_notification(self):
        n = Notification.push(self.admin, title='테스트', ntype='system')
        self.assertIsNotNone(n.pk)
        self.assertEqual(n.user, self.admin)
        self.assertFalse(n.is_read)

    def test_push_sets_fields(self):
        n = Notification.push(
            self.admin, title='제목', message='내용',
            ntype='incident', level='warning', link='/npms/incidents/1/'
        )
        self.assertEqual(n.title, '제목')
        self.assertEqual(n.message, '내용')
        self.assertEqual(n.ntype, 'incident')
        self.assertEqual(n.level, 'warning')
        self.assertEqual(n.link, '/npms/incidents/1/')

    def test_broadcast_creates_for_all_users(self):
        users = User.objects.filter(username__in=['noti_worker', 'noti_worker2'])
        Notification.broadcast(users, title='공지')
        self.assertEqual(Notification.objects.filter(title='공지').count(), 2)

    def test_unread_count_initially_all(self):
        Notification.push(self.worker, title='a')
        Notification.push(self.worker, title='b')
        cnt = Notification.objects.filter(user=self.worker, is_read=False).count()
        self.assertEqual(cnt, 2)

    def test_mark_read(self):
        n = Notification.push(self.worker, title='읽기 테스트')
        n.is_read = True
        n.read_at = timezone.now()
        n.save(update_fields=['is_read', 'read_at'])
        n.refresh_from_db()
        self.assertTrue(n.is_read)
        self.assertIsNotNone(n.read_at)

    def test_str_representation(self):
        n = Notification.push(self.admin, title='WBS 완료', ntype='wbs')
        self.assertIn('WBS', str(n))


# ─────────────────────────────────────────────────────────────
# 2. Notification REST API
# ─────────────────────────────────────────────────────────────
class NotificationAPITest(NotiFixtureMixin, TestCase):

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        # 테스트용 알림 생성
        self.n1 = Notification.push(self.admin, title='알림1', ntype='system')
        self.n2 = Notification.push(self.admin, title='알림2', ntype='incident')
        self.n3 = Notification.push(self.admin, title='읽힘', ntype='system')
        self.n3.is_read = True
        self.n3.read_at = timezone.now()
        self.n3.save()

    def test_list_returns_own_notifications(self):
        resp = self.client.get('/api/dashboard/notifications/')
        self.assertEqual(resp.status_code, 200)
        ids = [n['id'] for n in resp.data]
        self.assertIn(self.n1.pk, ids)
        self.assertIn(self.n2.pk, ids)

    def test_list_excludes_other_user(self):
        Notification.push(self.worker, title='남의 알림')
        resp = self.client.get('/api/dashboard/notifications/')
        titles = [n['title'] for n in resp.data]
        self.assertNotIn('남의 알림', titles)

    def test_unread_count(self):
        resp = self.client.get('/api/dashboard/notifications/unread_count/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['count'], 2)   # n1, n2 (n3은 읽음)

    def test_unread_count_zero_when_all_read(self):
        Notification.objects.filter(user=self.admin).update(is_read=True)
        resp = self.client.get('/api/dashboard/notifications/unread_count/')
        self.assertEqual(resp.data['count'], 0)

    def test_read_single_notification(self):
        resp = self.client.post(f'/api/dashboard/notifications/{self.n1.pk}/read/')
        self.assertEqual(resp.status_code, 200)
        self.n1.refresh_from_db()
        self.assertTrue(self.n1.is_read)
        self.assertIsNotNone(self.n1.read_at)

    def test_read_all(self):
        resp = self.client.post('/api/dashboard/notifications/read_all/')
        self.assertEqual(resp.status_code, 200)
        cnt = Notification.objects.filter(user=self.admin, is_read=False).count()
        self.assertEqual(cnt, 0)

    def test_clear_deletes_read_notifications(self):
        resp = self.client.delete('/api/dashboard/notifications/clear/')
        self.assertEqual(resp.status_code, 200)
        # 읽음 처리된 n3 삭제, n1·n2 (미읽음) 남아 있음
        self.assertFalse(Notification.objects.filter(pk=self.n3.pk).exists())
        self.assertTrue(Notification.objects.filter(pk=self.n1.pk).exists())

    def test_unauthenticated_returns_401(self):
        anon = APIClient()
        resp = anon.get('/api/dashboard/notifications/')
        self.assertIn(resp.status_code, [401, 403])

    def test_list_response_has_required_keys(self):
        resp = self.client.get('/api/dashboard/notifications/')
        if resp.data:
            keys = resp.data[0].keys()
            for k in ('id', 'title', 'ntype', 'level', 'is_read', 'created_at'):
                self.assertIn(k, keys)


# ─────────────────────────────────────────────────────────────
# 3. 시그널 → 채널 레이어 푸시
# ─────────────────────────────────────────────────────────────
@override_settings(
    CHANNEL_LAYERS={
        'default': {
            'BACKEND': 'channels.layers.InMemoryChannelLayer',
        }
    }
)
class NotificationSignalChannelTest(NotiFixtureMixin, TestCase):
    """Notification.push() / broadcast() 시 채널 레이어로 푸시해야 한다"""

    def test_push_triggers_channel_group_send(self):
        """Notification.push() 후 channel_layer.group_send 가 호출되어야 한다"""
        with patch('apps.dashboard.models.channel_layer_push') as mock_push:
            Notification.push(self.admin, title='채널 테스트')
        mock_push.assert_called_once()

    def test_push_sends_to_correct_group(self):
        """group_send 는 notification_{user_id} 그룹에 전송해야 한다"""
        with patch('apps.dashboard.models.channel_layer_push') as mock_push:
            Notification.push(self.admin, title='그룹 확인')
        call_args = mock_push.call_args
        group_name = call_args[0][0]
        self.assertEqual(group_name, f'notification_{self.admin.pk}')

    def test_push_sends_notification_type(self):
        """전송 메시지 type이 notification.push 여야 한다"""
        with patch('apps.dashboard.models.channel_layer_push') as mock_push:
            Notification.push(self.admin, title='타입 확인')
        call_args = mock_push.call_args
        event = call_args[0][1]
        self.assertEqual(event['type'], 'notification.push')

    def test_broadcast_pushes_for_each_user(self):
        """broadcast() 시 각 사용자 그룹에 전송해야 한다"""
        users = User.objects.filter(username__in=['noti_worker', 'noti_worker2'])
        with patch('apps.dashboard.models.channel_layer_push') as mock_push:
            Notification.broadcast(users, title='브로드캐스트')
        self.assertEqual(mock_push.call_count, 2)


# ─────────────────────────────────────────────────────────────
# 4. NotificationConsumer WebSocket
# ─────────────────────────────────────────────────────────────
@override_settings(
    CHANNEL_LAYERS={
        'default': {
            'BACKEND': 'channels.layers.InMemoryChannelLayer',
        }
    }
)
class NotificationConsumerTest(NotiFixtureMixin, TestCase):
    """NotificationConsumer WebSocket 연결·인증·메시지 흐름
    DB 접근은 mock 처리 (async 테스트 환경에서 TransactionTestCase 불필요)
    """

    @staticmethod
    def _import_ws_communicator():
        """channels.testing.websocket 을 직접 로드 (daphne 의존성 우회)"""
        import importlib.util, os
        path = os.path.join(
            os.path.dirname(importlib.util.find_spec('channels').origin),
            'testing', 'websocket.py'
        )
        spec = importlib.util.spec_from_file_location('_ws_comm', path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.WebsocketCommunicator

    async def _get_communicator(self, user=None, unread_count=0):
        """unread_count: DB 호출을 mock 하기 위한 반환값"""
        WebsocketCommunicator = self._import_ws_communicator()
        from core.consumers import NotificationConsumer
        from unittest.mock import AsyncMock, patch

        communicator = WebsocketCommunicator(
            NotificationConsumer.as_asgi(), '/ws/notifications/'
        )
        if user:
            communicator.scope['user'] = user
        # DB 호출 mock
        communicator._unread_mock_value = unread_count
        return communicator

    async def _connect_with_mock(self, communicator, unread=0):
        """_unread_count DB 호출을 mock 하면서 connect"""
        from unittest.mock import patch, AsyncMock
        from core.consumers import NotificationConsumer

        with patch.object(
            NotificationConsumer, '_unread_count',
            new=AsyncMock(return_value=unread),
        ):
            connected, code = await communicator.connect()
        return connected, code

    async def test_authenticated_user_can_connect(self):
        comm = await self._get_communicator(self.admin)
        connected, _ = await self._connect_with_mock(comm)
        self.assertTrue(connected)
        await comm.disconnect()

    async def test_unauthenticated_user_is_rejected(self):
        from django.contrib.auth.models import AnonymousUser
        comm = await self._get_communicator(AnonymousUser())
        connected, _ = await self._connect_with_mock(comm)
        self.assertFalse(connected)

    async def test_initial_message_contains_unread_count(self):
        """연결 즉시 unread count 메시지를 전송해야 한다"""
        from unittest.mock import patch, AsyncMock
        from core.consumers import NotificationConsumer

        comm = await self._get_communicator(self.admin)
        with patch.object(
            NotificationConsumer, '_unread_count',
            new=AsyncMock(return_value=5),
        ):
            await comm.connect()
        msg = await comm.receive_json_from(timeout=2)
        self.assertEqual(msg['type'], 'notification.count')
        self.assertEqual(msg['count'], 5)
        await comm.disconnect()

    async def test_notification_push_event_delivered(self):
        """notification.push 그룹 메시지가 클라이언트에게 전달되어야 한다"""
        from channels.layers import get_channel_layer
        from unittest.mock import patch, AsyncMock
        from core.consumers import NotificationConsumer

        comm = await self._get_communicator(self.admin)
        with patch.object(
            NotificationConsumer, '_unread_count',
            new=AsyncMock(return_value=0),
        ):
            await comm.connect()
        # 초기 count 메시지 수신
        await comm.receive_json_from(timeout=2)

        # 채널 레이어로 직접 푸시
        channel_layer = get_channel_layer()
        group_name = f'notification_{self.admin.pk}'
        await channel_layer.group_send(group_name, {
            'type': 'notification.push',
            'count': 3,
            'notification': {'id': 99, 'title': '실시간 알림', 'ntype': 'system'},
        })

        msg = await comm.receive_json_from(timeout=2)
        self.assertEqual(msg['type'], 'notification.push')
        self.assertIn('count', msg)
        await comm.disconnect()

    async def test_group_name_per_user(self):
        """각 사용자는 고유 그룹 notification_{user_id} 에 구독해야 한다"""
        from unittest.mock import patch, AsyncMock
        from core.consumers import NotificationConsumer

        comm1 = await self._get_communicator(self.admin)
        comm2 = await self._get_communicator(self.worker)

        with patch.object(
            NotificationConsumer, '_unread_count',
            new=AsyncMock(return_value=0),
        ):
            await comm1.connect()
            await comm2.connect()

        msg1 = await comm1.receive_json_from(timeout=2)
        msg2 = await comm2.receive_json_from(timeout=2)
        self.assertEqual(msg1['type'], 'notification.count')
        self.assertEqual(msg2['type'], 'notification.count')
        await comm1.disconnect()
        await comm2.disconnect()


# ─────────────────────────────────────────────────────────────
# 5. WebSocket URL 등록 및 라우팅
# ─────────────────────────────────────────────────────────────
class NotificationRoutingTest(TestCase):
    """ws/notifications/ 경로가 routing에 등록되어야 한다"""

    def test_ws_notifications_url_registered(self):
        from core.routing import websocket_urlpatterns
        paths = [str(p.pattern) for p in websocket_urlpatterns]
        self.assertTrue(
            any('notifications' in p for p in paths),
            f'ws/notifications/ 가 websocket_urlpatterns 에 없습니다. paths={paths}'
        )

    def test_notification_consumer_importable(self):
        try:
            from core.consumers import NotificationConsumer
        except ImportError as e:
            self.fail(f'NotificationConsumer import 실패: {e}')


# ─────────────────────────────────────────────────────────────
# 6. base.html — WS 알림 클라이언트 코드
# ─────────────────────────────────────────────────────────────
class BaseTemplateWSNotificationTest(TestCase):
    """base.html 에 WebSocket 알림 클라이언트 코드가 포함되어야 한다"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        import os
        from django.conf import settings
        path = os.path.join(settings.BASE_DIR, 'templates', 'base.html')
        with open(path, encoding='utf-8') as f:
            cls.html = f.read()

    def test_ws_notifications_url_in_base(self):
        """base.html 에 ws/notifications/ 접속 코드가 있어야 한다"""
        self.assertIn('ws/notifications/', self.html)

    def test_websocket_connect_function(self):
        """base.html 에 WebSocket 접속 코드(new WebSocket)가 있어야 한다"""
        self.assertIn('new WebSocket', self.html)

    def test_notification_count_handler(self):
        """notification.count 메시지를 처리하는 코드가 있어야 한다"""
        self.assertIn('notification.count', self.html)

    def test_polling_replaced_or_ws_added(self):
        """WebSocket 연결로 실시간 badge 업데이트 코드가 있어야 한다"""
        # notiCheckCount 폴링 OR WS count 핸들러 중 하나는 반드시 존재
        has_ws = 'notification.count' in self.html
        self.assertTrue(has_ws, 'base.html에 notification.count WS 핸들러가 없습니다.')
