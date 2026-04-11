"""
모바일 장애 접수 페이지 테스트
"""
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from apps.incidents.models import Incident, IncidentCategory, IncidentSubcategory
from apps.schools.models import School, SupportCenter, SchoolType

User = get_user_model()


class IncidentCreatePageTest(TestCase):
    """장애 접수 페이지 렌더링 테스트"""

    def setUp(self):
        self.client = Client(SERVER_NAME='localhost')
        self.worker = User.objects.create_user(
            username='worker1', email='w1@test.com',
            password='pass123', name='작업자1', role='worker',
        )
        self.client.force_login(self.worker)

    def test_page_returns_200(self):
        resp = self.client.get('/mobile/incidents/create/')
        self.assertEqual(resp.status_code, 200)

    def test_page_contains_priority_choices(self):
        """우선순위 선택 항목이 컨텍스트에 포함되는지 확인"""
        resp = self.client.get('/mobile/incidents/create/')
        self.assertIn('priority_choices', resp.context)
        labels = [label for _, label in resp.context['priority_choices']]
        self.assertIn('긴급', labels)
        self.assertIn('보통', labels)

    def test_page_contains_fault_type_choices(self):
        """장애 유형 선택 항목이 컨텍스트에 포함되는지 확인"""
        resp = self.client.get('/mobile/incidents/create/')
        self.assertIn('fault_type_choices', resp.context)

    def test_page_contains_contact_method_choices(self):
        """접수 방법 선택 항목이 컨텍스트에 포함되는지 확인"""
        resp = self.client.get('/mobile/incidents/create/')
        self.assertIn('contact_method_choices', resp.context)

    def test_page_has_school_select(self):
        """학교 선택 요소가 HTML에 존재하는지 확인"""
        resp = self.client.get('/mobile/incidents/create/')
        self.assertContains(resp, 'id="f-school"')

    def test_page_has_category_select(self):
        """장애 유형 선택 요소가 HTML에 존재하는지 확인"""
        resp = self.client.get('/mobile/incidents/create/')
        self.assertContains(resp, 'id="f-category"')

    def test_page_has_submit_button(self):
        """접수 버튼이 HTML에 존재하는지 확인"""
        resp = self.client.get('/mobile/incidents/create/')
        self.assertContains(resp, '장애 접수')

    def test_page_has_required_fields(self):
        """필수 입력 항목이 모두 HTML에 존재하는지 확인"""
        resp = self.client.get('/mobile/incidents/create/')
        self.assertContains(resp, 'f-requester-name')
        self.assertContains(resp, 'f-requester-phone')
        self.assertContains(resp, 'f-description')

    def test_unauthenticated_redirects(self):
        """비로그인 시 로그인 페이지로 리다이렉트"""
        c = Client(SERVER_NAME='localhost')
        resp = c.get('/mobile/incidents/create/')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('login', resp['Location'])
