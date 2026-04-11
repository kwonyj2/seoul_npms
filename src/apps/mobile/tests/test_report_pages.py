"""
모바일 설치 확인서 페이지 테스트
"""
from django.test import TestCase, Client
from django.contrib.auth import get_user_model

User = get_user_model()


class ReportCablePageTest(TestCase):
    """포설 확인서 모바일 페이지 테스트"""

    def setUp(self):
        self.client = Client(SERVER_NAME='localhost')
        self.worker = User.objects.create_user(
            username='worker1', email='w1@test.com',
            password='pass123', name='작업자1', role='worker',
        )
        self.client.force_login(self.worker)

    def test_page_returns_200(self):
        resp = self.client.get('/mobile/reports/cable/')
        self.assertEqual(resp.status_code, 200)

    def test_page_has_template_id_in_context(self):
        """케이블 템플릿 ID가 컨텍스트에 포함되는지 확인"""
        resp = self.client.get('/mobile/reports/cable/')
        self.assertIn('template_id', resp.context)

    def test_page_has_report_type_in_context(self):
        resp = self.client.get('/mobile/reports/cable/')
        self.assertIn('report_type', resp.context)
        self.assertEqual(resp.context['report_type'], 'cable')

    def test_page_has_signature_canvas(self):
        """서명 캔버스가 HTML에 존재하는지 확인"""
        resp = self.client.get('/mobile/reports/cable/')
        self.assertContains(resp, 'signature-canvas')

    def test_page_has_report_list_container(self):
        """보고서 목록 컨테이너가 HTML에 존재하는지 확인"""
        resp = self.client.get('/mobile/reports/cable/')
        self.assertContains(resp, 'report-list-wrap')

    def test_page_has_sign_submit_button(self):
        """서명 제출 버튼이 HTML에 존재하는지 확인"""
        resp = self.client.get('/mobile/reports/cable/')
        self.assertContains(resp, 'btn-sign-submit')

    def test_page_has_clear_button(self):
        """서명 지우기 버튼이 HTML에 존재하는지 확인"""
        resp = self.client.get('/mobile/reports/cable/')
        self.assertContains(resp, 'btn-sign-clear')

    def test_unauthenticated_redirects(self):
        c = Client(SERVER_NAME='localhost')
        resp = c.get('/mobile/reports/cable/')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('login', resp['Location'])


class ReportSwitchPageTest(TestCase):
    """스위치 설치 확인서 모바일 페이지 테스트"""

    def setUp(self):
        self.client = Client(SERVER_NAME='localhost')
        self.worker = User.objects.create_user(
            username='worker2', email='w2@test.com',
            password='pass123', name='작업자2', role='worker',
        )
        self.client.force_login(self.worker)

    def test_page_returns_200(self):
        resp = self.client.get('/mobile/reports/switch/')
        self.assertEqual(resp.status_code, 200)

    def test_page_has_template_id_in_context(self):
        resp = self.client.get('/mobile/reports/switch/')
        self.assertIn('template_id', resp.context)

    def test_page_has_report_type_in_context(self):
        resp = self.client.get('/mobile/reports/switch/')
        self.assertIn('report_type', resp.context)
        self.assertEqual(resp.context['report_type'], 'switch_install')

    def test_page_has_signature_canvas(self):
        resp = self.client.get('/mobile/reports/switch/')
        self.assertContains(resp, 'signature-canvas')

    def test_page_has_report_list_container(self):
        resp = self.client.get('/mobile/reports/switch/')
        self.assertContains(resp, 'report-list-wrap')

    def test_page_has_sign_submit_button(self):
        resp = self.client.get('/mobile/reports/switch/')
        self.assertContains(resp, 'btn-sign-submit')

    def test_page_has_clear_button(self):
        resp = self.client.get('/mobile/reports/switch/')
        self.assertContains(resp, 'btn-sign-clear')

    def test_unauthenticated_redirects(self):
        c = Client(SERVER_NAME='localhost')
        resp = c.get('/mobile/reports/switch/')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('login', resp['Location'])
