"""
Phase 8-2: 관리자 대시보드 고도화 테스트

테스트 범위:
  1. 시스템 헬스 API (CPU/메모리/디스크)
  2. 스토리지 사용량 API (NAS)
  3. 배치 작업 수동 트리거 API
  4. DB 테이블별 레코드 수
  5. 실시간 접속 현황 API
"""
from django.test import TestCase, Client
from apps.accounts.models import User


def make_admin(username='dashboard_admin'):
    return User.objects.create_user(
        username=username, email=f'{username}@test.com',
        name='관리자', password='TestPass1!', role='admin',
    )


# ─────────────────────────────────────────────────────────────
# 1. 시스템 헬스 API
# ─────────────────────────────────────────────────────────────
class SystemHealthApiTest(TestCase):
    """GET /api/sysconfig/health/ — CPU·메모리·디스크 현황"""

    def setUp(self):
        self.client = Client()
        self.admin = make_admin()
        self.client.force_login(self.admin)

    def test_health_endpoint_returns_200(self):
        resp = self.client.get('/api/sysconfig/health/')
        self.assertEqual(resp.status_code, 200,
            f'/api/sysconfig/health/ 응답코드: {resp.status_code}')

    def test_health_response_has_cpu(self):
        resp = self.client.get('/api/sysconfig/health/')
        import json
        data = json.loads(resp.content)
        self.assertIn('cpu', data, 'health 응답에 cpu 항목이 없습니다.')

    def test_health_response_has_memory(self):
        resp = self.client.get('/api/sysconfig/health/')
        import json
        data = json.loads(resp.content)
        self.assertIn('memory', data, 'health 응답에 memory 항목이 없습니다.')

    def test_health_response_has_disk(self):
        resp = self.client.get('/api/sysconfig/health/')
        import json
        data = json.loads(resp.content)
        self.assertIn('disk', data, 'health 응답에 disk 항목이 없습니다.')

    def test_health_requires_auth(self):
        c = Client()  # 비인증
        resp = c.get('/api/sysconfig/health/')
        self.assertIn(resp.status_code, [401, 302])


# ─────────────────────────────────────────────────────────────
# 2. 스토리지 사용량 API
# ─────────────────────────────────────────────────────────────
class StorageUsageApiTest(TestCase):
    """GET /api/sysconfig/storage/ — NAS 용량 현황"""

    def setUp(self):
        self.client = Client()
        self.admin = make_admin('storage_admin')
        self.client.force_login(self.admin)

    def test_storage_endpoint_returns_200(self):
        resp = self.client.get('/api/sysconfig/storage/')
        self.assertEqual(resp.status_code, 200)

    def test_storage_response_has_total_and_used(self):
        resp = self.client.get('/api/sysconfig/storage/')
        import json
        data = json.loads(resp.content)
        self.assertIn('total', data, 'storage 응답에 total이 없습니다.')
        self.assertIn('used', data,  'storage 응답에 used가 없습니다.')

    def test_storage_response_has_nas_path(self):
        resp = self.client.get('/api/sysconfig/storage/')
        import json
        data = json.loads(resp.content)
        self.assertIn('nas_path', data, 'storage 응답에 nas_path가 없습니다.')


# ─────────────────────────────────────────────────────────────
# 3. 배치 작업 수동 트리거
# ─────────────────────────────────────────────────────────────
class BatchTriggerApiTest(TestCase):
    """POST /api/sysconfig/trigger-task/ — 배치 작업 수동 트리거"""

    def setUp(self):
        self.client = Client()
        self.admin = make_admin('batch_admin')
        self.client.force_login(self.admin)

    def test_trigger_endpoint_exists(self):
        """트리거 API 엔드포인트가 있어야 한다 (405 제외 모든 코드는 엔드포인트 존재 의미)"""
        import json
        resp = self.client.post(
            '/api/sysconfig/trigger-task/',
            data=json.dumps({'task': 'sync_nas_filesystem'}),
            content_type='application/json',
        )
        self.assertNotEqual(resp.status_code, 404,
            '/api/sysconfig/trigger-task/ 엔드포인트가 없습니다.')

    def test_trigger_unknown_task_returns_400(self):
        """알 수 없는 태스크 이름은 400 반환"""
        import json
        resp = self.client.post(
            '/api/sysconfig/trigger-task/',
            data=json.dumps({'task': 'nonexistent_task_xyz'}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 400)

    def test_trigger_requires_admin(self):
        """일반 사용자는 트리거 불가"""
        worker = User.objects.create_user(
            username='trigger_worker', email='tw@test.com',
            name='기사', password='TestPass1!', role='worker',
        )
        c = Client()
        c.force_login(worker)
        import json
        resp = c.post(
            '/api/sysconfig/trigger-task/',
            data=json.dumps({'task': 'sync_nas_filesystem'}),
            content_type='application/json',
        )
        self.assertIn(resp.status_code, [401, 403])


# ─────────────────────────────────────────────────────────────
# 4. DB 테이블 통계 (system_info 확장)
# ─────────────────────────────────────────────────────────────
class SystemInfoDbStatsTest(TestCase):
    """GET /api/sysconfig/info/ — DB 테이블별 레코드 수"""

    def setUp(self):
        self.client = Client()
        self.admin = make_admin('info_admin')
        self.client.force_login(self.admin)

    def test_system_info_returns_200(self):
        resp = self.client.get('/api/sysconfig/info/')
        self.assertEqual(resp.status_code, 200)

    def test_system_info_has_counts(self):
        resp = self.client.get('/api/sysconfig/info/')
        import json
        data = json.loads(resp.content)
        self.assertIn('counts', data, 'system_info에 counts가 없습니다.')

    def test_system_info_has_server(self):
        resp = self.client.get('/api/sysconfig/info/')
        import json
        data = json.loads(resp.content)
        self.assertIn('server', data, 'system_info에 server가 없습니다.')


# ─────────────────────────────────────────────────────────────
# 5. 실시간 접속 현황
# ─────────────────────────────────────────────────────────────
class RealtimeSessionApiTest(TestCase):
    """GET /api/sysconfig/access-log/?kind=session — 접속 현황"""

    def setUp(self):
        self.client = Client()
        self.admin = make_admin('session_admin')
        self.client.force_login(self.admin)

    def test_session_kind_returns_200(self):
        resp = self.client.get('/api/sysconfig/access-log/?kind=session')
        self.assertEqual(resp.status_code, 200)

    def test_session_response_has_rows(self):
        resp = self.client.get('/api/sysconfig/access-log/?kind=session')
        import json
        data = json.loads(resp.content)
        self.assertIn('rows', data)
