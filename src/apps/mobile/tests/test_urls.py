"""
모바일 URL 구조 테스트
- reverse()는 FORCE_SCRIPT_NAME='/npms' 적용 → /npms/mobile/... 반환
- test client는 Django URL 패턴 직접 접근 → /mobile/... 사용
"""
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

User = get_user_model()


class MobileURLResolutionTest(TestCase):
    """reverse()로 URL이 올바르게 등록되었는지 확인"""

    def test_mobile_dashboard_url_resolves(self):
        self.assertEqual(reverse('mobile:dashboard'), '/npms/mobile/')

    def test_mobile_incident_list_url_resolves(self):
        self.assertEqual(reverse('mobile:incident-list'), '/npms/mobile/incidents/')

    def test_mobile_incident_create_url_resolves(self):
        self.assertEqual(reverse('mobile:incident-create'), '/npms/mobile/incidents/create/')

    def test_mobile_incident_detail_url_resolves(self):
        self.assertEqual(reverse('mobile:incident-detail', args=[1]), '/npms/mobile/incidents/1/')

    def test_mobile_report_cable_url_resolves(self):
        self.assertEqual(reverse('mobile:report-cable'), '/npms/mobile/reports/cable/')

    def test_mobile_report_switch_url_resolves(self):
        self.assertEqual(reverse('mobile:report-switch'), '/npms/mobile/reports/switch/')


class MobileURLAccessTest(TestCase):
    """비로그인 시 로그인 페이지로 리다이렉트 확인"""

    def setUp(self):
        self.client = Client(SERVER_NAME='localhost')

    def test_mobile_dashboard_redirects_to_login(self):
        resp = self.client.get('/mobile/')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('login', resp['Location'])

    def test_mobile_incidents_redirects_to_login(self):
        resp = self.client.get('/mobile/incidents/')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('login', resp['Location'])


class MobileURLAuthenticatedTest(TestCase):
    """로그인 후 200 응답 확인"""

    def setUp(self):
        self.client = Client(SERVER_NAME='localhost')
        self.worker = User.objects.create_user(
            username='testworker',
            email='testworker@test.com',
            password='testpass123',
            name='테스트작업자',
            role='worker',
        )
        self.client.force_login(self.worker)

    def test_mobile_dashboard_returns_200(self):
        self.assertEqual(self.client.get('/mobile/').status_code, 200)

    def test_mobile_incident_list_returns_200(self):
        self.assertEqual(self.client.get('/mobile/incidents/').status_code, 200)

    def test_mobile_incident_create_returns_200(self):
        self.assertEqual(self.client.get('/mobile/incidents/create/').status_code, 200)

    def test_mobile_report_cable_returns_200(self):
        self.assertEqual(self.client.get('/mobile/reports/cable/').status_code, 200)

    def test_mobile_report_switch_returns_200(self):
        self.assertEqual(self.client.get('/mobile/reports/switch/').status_code, 200)
