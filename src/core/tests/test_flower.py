"""
Flower Celery 모니터링 테스트 — Phase 2-2
"""
from django.test import TestCase, Client
from django.contrib.auth import get_user_model

User = get_user_model()


class FlowerRequirementsTest(TestCase):
    """requirements.txt에 flower 포함 여부 확인"""

    def _read_requirements(self):
        import os
        req_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'requirements.txt'
        )
        with open(os.path.abspath(req_path)) as f:
            return f.read().lower()

    def test_flower_in_requirements(self):
        self.assertIn('flower', self._read_requirements())


class CelerySettingsTest(TestCase):
    """Celery 기본 설정 확인"""

    def test_celery_broker_url_set(self):
        from django.conf import settings
        self.assertTrue(hasattr(settings, 'CELERY_BROKER_URL'))
        self.assertIsNotNone(settings.CELERY_BROKER_URL)

    def test_celery_result_backend_set(self):
        from django.conf import settings
        self.assertTrue(hasattr(settings, 'CELERY_RESULT_BACKEND'))

    def test_celery_app_importable(self):
        from config.celery import app
        self.assertIsNotNone(app)
        self.assertEqual(app.main, 'npms')

    def test_flower_url_setting_exists(self):
        from django.conf import settings
        self.assertTrue(hasattr(settings, 'FLOWER_URL'))

    def test_django_celery_beat_installed(self):
        from django.conf import settings
        self.assertIn('django_celery_beat', settings.INSTALLED_APPS)

    def test_django_celery_results_installed(self):
        from django.conf import settings
        self.assertIn('django_celery_results', settings.INSTALLED_APPS)


class CeleryStatusAPITest(TestCase):
    """Celery 워커 상태 API 엔드포인트 테스트"""

    def setUp(self):
        self.client = Client(SERVER_NAME='localhost')
        self.admin = User.objects.create_user(
            username='sysadmin', email='admin@test.com',
            password='pass123', name='관리자', role='admin',
        )
        self.client.force_login(self.admin)

    def test_celery_status_endpoint_exists(self):
        resp = self.client.get('/api/sysconfig/celery-status/')
        self.assertNotEqual(resp.status_code, 404)

    def test_celery_status_returns_200(self):
        resp = self.client.get('/api/sysconfig/celery-status/')
        self.assertEqual(resp.status_code, 200)

    def test_celery_status_returns_json(self):
        resp = self.client.get('/api/sysconfig/celery-status/')
        self.assertEqual(resp['Content-Type'], 'application/json')

    def test_celery_status_has_broker_key(self):
        import json
        resp = self.client.get('/api/sysconfig/celery-status/')
        data = json.loads(resp.content)
        self.assertIn('broker', data)

    def test_celery_status_has_flower_url_key(self):
        import json
        resp = self.client.get('/api/sysconfig/celery-status/')
        data = json.loads(resp.content)
        self.assertIn('flower_url', data)

    def test_celery_status_has_workers_key(self):
        import json
        resp = self.client.get('/api/sysconfig/celery-status/')
        data = json.loads(resp.content)
        self.assertIn('workers', data)

    def test_unauthenticated_returns_403_or_302(self):
        c = Client(SERVER_NAME='localhost')
        resp = c.get('/api/sysconfig/celery-status/')
        self.assertIn(resp.status_code, [302, 403, 401])
