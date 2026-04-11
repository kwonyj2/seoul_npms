"""
Phase 4-3: 감사 로그 추가 테스트

테스트 범위:
  1. AuditLogMiddleware — DB UserActivityLog 기록 (POST/PUT/PATCH/DELETE)
  2. AuditLogMiddleware — GET 은 기록 안 함
  3. AuditLogMiddleware — 비인증 사용자는 기록 안 함
  4. 로그인 성공 → UserActivityLog 'login' 기록
  5. 로그인 실패 → UserActivityLog 'login' 기록 (실패)
  6. 로그아웃 → UserActivityLog 'logout' 기록
  7. action→method 매핑 검증
  8. target 필드 — URL 경로에서 추출
  9. ip_address 저장
  10. sysconfig access_log API — UserActivityLog 조회
"""
from django.test import TestCase, RequestFactory, Client, override_settings
from django.contrib.auth.models import AnonymousUser
from django.urls import reverse

from apps.accounts.models import User, UserActivityLog, LoginHistory


# ─────────────────────────────────────────────────────────────
# 1~3. AuditLogMiddleware → UserActivityLog DB 기록
# ─────────────────────────────────────────────────────────────
class AuditLogMiddlewareDBTest(TestCase):
    """AuditLogMiddleware 가 UserActivityLog 에 DB 레코드를 남겨야 한다"""

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            username='audit_admin', email='audit_admin@test.com',
            password='pass', role='admin',
        )

    def _make_middleware(self, method, path, status_code=200):
        from core.middleware.audit import AuditLogMiddleware
        from unittest.mock import MagicMock

        mock_response = MagicMock()
        mock_response.status_code = status_code
        get_response = MagicMock(return_value=mock_response)
        mw = AuditLogMiddleware(get_response)

        factory = RequestFactory()
        req = getattr(factory, method.lower())(path)
        req.user = self.admin
        req.META['REMOTE_ADDR'] = '1.2.3.4'
        return mw, req

    def test_post_creates_activity_log(self):
        mw, req = self._make_middleware('POST', '/api/incidents/')
        mw(req)
        self.assertTrue(
            UserActivityLog.objects.filter(
                user=self.admin, action='create'
            ).exists()
        )

    def test_put_creates_update_log(self):
        mw, req = self._make_middleware('PUT', '/api/incidents/1/')
        mw(req)
        self.assertTrue(
            UserActivityLog.objects.filter(
                user=self.admin, action='update'
            ).exists()
        )

    def test_patch_creates_update_log(self):
        mw, req = self._make_middleware('PATCH', '/api/incidents/1/')
        mw(req)
        self.assertTrue(
            UserActivityLog.objects.filter(
                user=self.admin, action='update'
            ).exists()
        )

    def test_delete_creates_delete_log(self):
        mw, req = self._make_middleware('DELETE', '/api/incidents/1/')
        mw(req)
        self.assertTrue(
            UserActivityLog.objects.filter(
                user=self.admin, action='delete'
            ).exists()
        )

    def test_get_does_not_create_log(self):
        mw, req = self._make_middleware('GET', '/api/incidents/')
        before = UserActivityLog.objects.count()
        mw(req)
        self.assertEqual(UserActivityLog.objects.count(), before)

    def test_unauthenticated_does_not_create_log(self):
        from core.middleware.audit import AuditLogMiddleware
        from unittest.mock import MagicMock

        mock_response = MagicMock()
        mock_response.status_code = 401
        get_response = MagicMock(return_value=mock_response)
        mw = AuditLogMiddleware(get_response)

        factory = RequestFactory()
        req = factory.post('/api/incidents/')
        req.user = AnonymousUser()
        before = UserActivityLog.objects.count()
        mw(req)
        self.assertEqual(UserActivityLog.objects.count(), before)

    def test_target_extracted_from_path(self):
        mw, req = self._make_middleware('DELETE', '/api/incidents/42/')
        mw(req)
        log = UserActivityLog.objects.filter(
            user=self.admin, action='delete'
        ).latest('created_at')
        self.assertIn('incidents', log.target)

    def test_ip_address_saved(self):
        mw, req = self._make_middleware('POST', '/api/schools/')
        mw(req)
        log = UserActivityLog.objects.filter(
            user=self.admin, action='create'
        ).latest('created_at')
        self.assertEqual(log.ip_address, '1.2.3.4')

    def test_status_code_saved_in_detail(self):
        mw, req = self._make_middleware('POST', '/api/incidents/', status_code=201)
        mw(req)
        log = UserActivityLog.objects.filter(
            user=self.admin, action='create'
        ).latest('created_at')
        self.assertIn('201', log.detail)


# ─────────────────────────────────────────────────────────────
# 4~6. 로그인·로그아웃 → UserActivityLog
# ─────────────────────────────────────────────────────────────
class LoginLogoutActivityLogTest(TestCase):
    """로그인/로그아웃 시 UserActivityLog 기록"""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='login_user', email='login_user@test.com',
            password='testpass123', role='worker',
        )

    def test_login_success_creates_activity_log(self):
        c = Client()
        c.post('/accounts/login/', {
            'username': 'login_user',
            'password': 'testpass123',
        })
        self.assertTrue(
            UserActivityLog.objects.filter(
                user=self.user, action='login'
            ).exists()
        )

    def test_login_failure_creates_activity_log(self):
        """로그인 실패도 UserActivityLog에 기록되어야 한다"""
        c = Client()
        c.post('/accounts/login/', {
            'username': 'login_user',
            'password': 'wrong_password',
        })
        self.assertTrue(
            UserActivityLog.objects.filter(
                action='login'
            ).exists()
        )
        log = UserActivityLog.objects.filter(action='login').latest('created_at')
        # 실패 기록 — detail에 실패 표시
        self.assertIn('실패', log.detail)

    def test_login_success_detail_is_success(self):
        c = Client()
        c.post('/accounts/login/', {
            'username': 'login_user',
            'password': 'testpass123',
        })
        log = UserActivityLog.objects.filter(
            user=self.user, action='login'
        ).latest('created_at')
        self.assertIn('성공', log.detail)

    def test_logout_creates_activity_log(self):
        """로그아웃 시 UserActivityLog 'logout' 기록"""
        c = Client()
        c.post('/accounts/login/', {
            'username': 'login_user',
            'password': 'testpass123',
        })
        c.post('/accounts/logout/')
        self.assertTrue(
            UserActivityLog.objects.filter(
                user=self.user, action='logout'
            ).exists()
        )


# ─────────────────────────────────────────────────────────────
# 7. 메서드 → 액션 매핑
# ─────────────────────────────────────────────────────────────
class MethodActionMappingTest(TestCase):
    """HTTP 메서드 → UserActivityLog.action 매핑 검증"""

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            username='map_admin', email='map_admin@test.com',
            password='pass', role='admin',
        )

    def _run(self, method, path='/api/test/'):
        from core.middleware.audit import AuditLogMiddleware
        from unittest.mock import MagicMock

        mock_response = MagicMock()
        mock_response.status_code = 200
        mw = AuditLogMiddleware(lambda r: mock_response)
        factory = RequestFactory()
        req = getattr(factory, method.lower())(path)
        req.user = self.admin
        req.META['REMOTE_ADDR'] = '127.0.0.1'
        mw(req)
        return UserActivityLog.objects.filter(user=self.admin).latest('created_at')

    def test_post_maps_to_create(self):
        log = self._run('POST')
        self.assertEqual(log.action, 'create')

    def test_put_maps_to_update(self):
        log = self._run('PUT')
        self.assertEqual(log.action, 'update')

    def test_patch_maps_to_update(self):
        log = self._run('PATCH')
        self.assertEqual(log.action, 'update')

    def test_delete_maps_to_delete(self):
        log = self._run('DELETE')
        self.assertEqual(log.action, 'delete')


# ─────────────────────────────────────────────────────────────
# 8. sysconfig access_log API
# ─────────────────────────────────────────────────────────────
class SysconfigActivityLogAPITest(TestCase):
    """sysconfig access_log API 가 UserActivityLog 를 반환해야 한다"""

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            username='syslog_admin', email='syslog_admin@test.com',
            password='pass', role='admin',
        )
        UserActivityLog.objects.create(
            user=cls.admin, action='create',
            target='incidents/1', detail='status=201',
            ip_address='127.0.0.1',
        )

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.admin)

    def test_activity_kind_returns_logs(self):
        resp = self.client.get('/api/sysconfig/access-log/?kind=activity')
        self.assertEqual(resp.status_code, 200)
        import json
        data = json.loads(resp.content)
        self.assertGreater(data.get('total', 0), 0)

    def test_activity_row_has_required_keys(self):
        resp = self.client.get('/api/sysconfig/access-log/?kind=activity')
        import json
        data = json.loads(resp.content)
        if data.get('rows'):
            row = data['rows'][0]
            for k in ('username', 'name', 'action', 'target', 'created_at'):
                self.assertIn(k, row)
