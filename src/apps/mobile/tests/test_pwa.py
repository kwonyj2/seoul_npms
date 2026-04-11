"""
PWA manifest + 서비스워커 + 홈 화면 추가 테스트
"""
import json
from django.test import TestCase, Client
from django.contrib.auth import get_user_model

User = get_user_model()


class PWAManifestTest(TestCase):
    """manifest.json 응답 테스트"""

    def setUp(self):
        self.client = Client(SERVER_NAME='localhost')
        self.worker = User.objects.create_user(
            username='pwa1', email='pwa1@test.com',
            password='pass123', name='PWA테스터', role='worker',
        )
        self.client.force_login(self.worker)

    def test_manifest_returns_200(self):
        resp = self.client.get('/mobile/manifest.json')
        self.assertEqual(resp.status_code, 200)

    def test_manifest_content_type_is_json(self):
        resp = self.client.get('/mobile/manifest.json')
        self.assertIn('application/json', resp['Content-Type'])

    def test_manifest_has_name(self):
        resp = self.client.get('/mobile/manifest.json')
        data = json.loads(resp.content)
        self.assertIn('name', data)

    def test_manifest_has_start_url(self):
        resp = self.client.get('/mobile/manifest.json')
        data = json.loads(resp.content)
        self.assertIn('start_url', data)

    def test_manifest_display_is_standalone(self):
        resp = self.client.get('/mobile/manifest.json')
        data = json.loads(resp.content)
        self.assertEqual(data.get('display'), 'standalone')

    def test_manifest_has_theme_color(self):
        resp = self.client.get('/mobile/manifest.json')
        data = json.loads(resp.content)
        self.assertIn('theme_color', data)

    def test_manifest_accessible_without_login(self):
        c = Client(SERVER_NAME='localhost')
        resp = c.get('/mobile/manifest.json')
        self.assertEqual(resp.status_code, 200)


class PWAServiceWorkerTest(TestCase):
    """sw.js 서비스워커 응답 테스트"""

    def setUp(self):
        self.client = Client(SERVER_NAME='localhost')

    def test_sw_returns_200(self):
        resp = self.client.get('/mobile/sw.js')
        self.assertEqual(resp.status_code, 200)

    def test_sw_content_type_is_javascript(self):
        resp = self.client.get('/mobile/sw.js')
        self.assertIn('javascript', resp['Content-Type'])

    def test_sw_accessible_without_login(self):
        resp = self.client.get('/mobile/sw.js')
        self.assertEqual(resp.status_code, 200)

    def test_sw_contains_cache_logic(self):
        resp = self.client.get('/mobile/sw.js')
        self.assertIn(b'install', resp.content)
        self.assertIn(b'fetch', resp.content)


class PWABaseTemplateTest(TestCase):
    """base.html PWA 메타태그·링크 포함 테스트"""

    def setUp(self):
        self.client = Client(SERVER_NAME='localhost')
        self.worker = User.objects.create_user(
            username='pwa2', email='pwa2@test.com',
            password='pass123', name='PWA테스터2', role='worker',
        )
        self.client.force_login(self.worker)

    def test_dashboard_has_manifest_link(self):
        resp = self.client.get('/mobile/')
        self.assertContains(resp, 'rel="manifest"')

    def test_dashboard_has_sw_registration(self):
        resp = self.client.get('/mobile/')
        self.assertContains(resp, 'serviceWorker')

    def test_dashboard_has_theme_color_meta(self):
        resp = self.client.get('/mobile/')
        self.assertContains(resp, 'theme-color')

    def test_dashboard_has_apple_touch_icon(self):
        resp = self.client.get('/mobile/')
        self.assertContains(resp, 'apple-touch-icon')
