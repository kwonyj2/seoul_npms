"""
모바일 장애 처리 + 사진 촬영 페이지 테스트
"""
from django.test import TestCase, Client
from django.contrib.auth import get_user_model

User = get_user_model()


class IncidentDetailPageTest(TestCase):
    """장애 처리 페이지 렌더링 테스트"""

    def setUp(self):
        self.client = Client(SERVER_NAME='localhost')
        self.worker = User.objects.create_user(
            username='worker1', email='w1@test.com',
            password='pass123', name='작업자1', role='worker',
        )
        self.client.force_login(self.worker)

    def test_page_returns_200(self):
        resp = self.client.get('/mobile/incidents/1/')
        self.assertEqual(resp.status_code, 200)

    def test_page_has_incident_id_in_context(self):
        """pk가 컨텍스트에 전달되는지 확인"""
        resp = self.client.get('/mobile/incidents/99/')
        self.assertEqual(resp.context['pk'], 99)

    def test_page_has_status_choices_in_context(self):
        """상태 전이 정보가 컨텍스트에 포함되는지 확인"""
        resp = self.client.get('/mobile/incidents/1/')
        self.assertIn('status_labels', resp.context)
        self.assertIn('next_status', resp.context)

    def test_page_has_photo_stage_choices_in_context(self):
        """사진 단계 선택 항목이 컨텍스트에 포함되는지 확인"""
        resp = self.client.get('/mobile/incidents/1/')
        self.assertIn('photo_stage_choices', resp.context)

    def test_page_has_resolution_textarea(self):
        """처리 내용 입력 영역이 HTML에 존재하는지 확인"""
        resp = self.client.get('/mobile/incidents/1/')
        self.assertContains(resp, 'f-resolution')

    def test_page_has_photo_upload_input(self):
        """사진 업로드 입력이 HTML에 존재하는지 확인"""
        resp = self.client.get('/mobile/incidents/1/')
        self.assertContains(resp, 'capture="camera"')

    def test_page_has_photo_stage_selector(self):
        """작업전/작업후 단계 선택이 HTML에 존재하는지 확인"""
        resp = self.client.get('/mobile/incidents/1/')
        self.assertContains(resp, 'f-photo-stage')

    def test_page_has_status_transition_section(self):
        """상태 전이 버튼 영역이 HTML에 존재하는지 확인"""
        resp = self.client.get('/mobile/incidents/1/')
        self.assertContains(resp, 'btn-status')

    def test_page_has_before_after_photo_sections(self):
        """작업전/작업후 사진 구역이 HTML에 존재하는지 확인"""
        resp = self.client.get('/mobile/incidents/1/')
        self.assertContains(resp, '작업전')
        self.assertContains(resp, '작업후')

    def test_unauthenticated_redirects(self):
        """비로그인 시 로그인 페이지로 리다이렉트"""
        c = Client(SERVER_NAME='localhost')
        resp = c.get('/mobile/incidents/1/')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('login', resp['Location'])
