"""
Django Channels WebSocket 소비자
- 대시보드 실시간 갱신
- 장애 알림
- 개인 알림 실시간 푸시 (NotificationConsumer)
"""
import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async

logger = logging.getLogger(__name__)


class DashboardConsumer(AsyncWebsocketConsumer):
    """대시보드 실시간 갱신 컨슈머"""
    GROUP_NAME = 'dashboard'

    async def connect(self):
        if not self.scope['user'].is_authenticated:
            await self.close()
            return
        await self.channel_layer.group_add(self.GROUP_NAME, self.channel_name)
        await self.accept()
        # 연결 시 최신 데이터 즉시 전송
        data = await self.get_dashboard_data()
        await self.send(text_data=json.dumps({'type': 'dashboard.update', 'data': data}))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.GROUP_NAME, self.channel_name)

    async def receive(self, text_data):
        """클라이언트 요청 처리 (ping 등)"""
        try:
            msg = json.loads(text_data)
            if msg.get('type') == 'ping':
                await self.send(text_data=json.dumps({'type': 'pong'}))
            elif msg.get('type') == 'refresh':
                data = await self.get_dashboard_data()
                await self.send(text_data=json.dumps({'type': 'dashboard.update', 'data': data}))
        except Exception as e:
            logger.warning(f'WebSocket receive error: {e}')

    async def dashboard_update(self, event):
        """그룹 메시지 → 클라이언트 전송"""
        await self.send(text_data=json.dumps(event))

    async def incident_alert(self, event):
        """장애 알림"""
        await self.send(text_data=json.dumps(event))

    @database_sync_to_async
    def get_dashboard_data(self):
        from apps.dashboard.views import get_dashboard_data
        return get_dashboard_data()


class IncidentConsumer(AsyncWebsocketConsumer):
    """장애 상세 페이지 실시간 업데이트"""

    async def connect(self):
        if not self.scope['user'].is_authenticated:
            await self.close()
            return
        self.incident_id = self.scope['url_route']['kwargs']['incident_id']
        self.group_name  = f'incident_{self.incident_id}'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def incident_update(self, event):
        await self.send(text_data=json.dumps(event))


class NotificationConsumer(AsyncWebsocketConsumer):
    """개인 알림 실시간 WebSocket 컨슈머
    그룹명: notification_{user_id}
    """

    async def connect(self):
        if not self.scope['user'].is_authenticated:
            await self.close()
            return
        self.user = self.scope['user']
        self.group_name = f'notification_{self.user.pk}'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        # 연결 즉시 현재 미읽음 수 전송
        count = await self._unread_count()
        await self.send(text_data=json.dumps({
            'type': 'notification.count',
            'count': count,
        }))

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def notification_push(self, event):
        """채널 레이어 그룹 메시지 → 클라이언트 전달"""
        await self.send(text_data=json.dumps(event))

    @database_sync_to_async
    def _unread_count(self):
        from apps.dashboard.models import Notification
        return Notification.objects.filter(
            user=self.user, is_read=False
        ).count()
