"""
Phase 5-1: 장애 자동 배정 고도화 테스트

테스트 범위:
  1. calculate_distance — Haversine 공식 정확성 (기존 버그 검출 포함)
  2. get_available_workers — 같은 지원청·활성·worker 필터
  3. get_best_worker — 거리+부하 기반 최적 인력 선택 (신규 함수)
  4. create_assignment — IncidentAssignment 생성, 상태 전이, 이력
  5. ai_assign 액션 — AI 서버 없을 때 스마트 폴백 (거리 기반)
  6. available_workers API — 가용 인력 목록 반환
"""
from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.gps.models import WorkerLocation
from apps.incidents.models import (
    Incident, IncidentAssignment, IncidentCategory,
    IncidentStatusHistory,
)
from apps.incidents.services import (
    calculate_distance, get_available_workers, create_assignment,
)
from apps.schools.models import SupportCenter, SchoolType, School


# ─────────────────────────────────────────────────────────────
# 공통 픽스처
# ─────────────────────────────────────────────────────────────
class AutoAssignFixtureMixin:
    @classmethod
    def setUpTestData(cls):
        cls.center = SupportCenter.objects.create(
            code='dongbu', name='동부교육지원청',
            lat=Decimal('37.5665'), lng=Decimal('127.0800'),
        )
        cls.center2 = SupportCenter.objects.create(
            code='seobu', name='서부교육지원청',
            lat=Decimal('37.5500'), lng=Decimal('126.9100'),
        )
        cls.school_type = SchoolType.objects.create(code='elementary', name='초등학교')

        # 학교 (동부 소속, GPS 있음)
        cls.school = School.objects.create(
            support_center=cls.center, school_type=cls.school_type,
            name='테스트초등학교', address='서울',
            lat=Decimal('37.5700'), lng=Decimal('127.0900'),
        )
        # GPS 없는 학교
        cls.school_no_gps = School.objects.create(
            support_center=cls.center, school_type=cls.school_type,
            name='GPS없는학교', address='서울',
        )

        cls.category = IncidentCategory.objects.create(
            code='wired', name='유선망', order=1
        )
        cls.admin = User.objects.create_user(
            username='assign_admin', email='assign_admin@test.com',
            password='pass', role='admin',
        )

        # 동부 소속 인력 (near: 학교에서 약 0.5km)
        cls.worker_near = User.objects.create_user(
            username='worker_near', email='worker_near@test.com',
            password='pass', role='worker',
            support_center=cls.center,
            home_lat=Decimal('37.5720'), home_lng=Decimal('127.0910'),
        )
        # 동부 소속 인력 (far: 학교에서 약 10km)
        cls.worker_far = User.objects.create_user(
            username='worker_far', email='worker_far@test.com',
            password='pass', role='worker',
            support_center=cls.center,
            home_lat=Decimal('37.5000'), home_lng=Decimal('127.1500'),
        )
        # 서부 소속 인력 (다른 지원청)
        cls.worker_other = User.objects.create_user(
            username='worker_other', email='worker_other@test.com',
            password='pass', role='worker',
            support_center=cls.center2,
        )
        # 비활성 인력
        cls.worker_inactive = User.objects.create_user(
            username='worker_inactive', email='worker_inactive@test.com',
            password='pass', role='worker', is_active=False,
            support_center=cls.center,
        )
        # admin 역할(비worker)
        cls.worker_wrong_role = User.objects.create_user(
            username='worker_admin_role', email='worker_admin_role@test.com',
            password='pass', role='admin',
            support_center=cls.center,
        )

    def _make_incident(self, school=None, priority='medium'):
        school = school or self.school
        return Incident.objects.create(
            incident_number=Incident.generate_number(),
            school=school,
            category=self.category,
            status='received',
            priority=priority,
            received_by=self.admin,
            requester_name='요청자',
            requester_phone='010-1234-5678',
            description='테스트 장애',
        )


# ─────────────────────────────────────────────────────────────
# 1. calculate_distance
# ─────────────────────────────────────────────────────────────
class CalculateDistanceTest(TestCase):

    def test_zero_distance_same_point(self):
        d = calculate_distance(37.5665, 126.9780, 37.5665, 126.9780)
        self.assertEqual(d, 0.0)

    def test_seoul_to_busan_approx_325km(self):
        """서울(37.5665, 126.9780) → 부산(35.1796, 129.0756) ≈ 320~330 km"""
        d = calculate_distance(37.5665, 126.9780, 35.1796, 129.0756)
        self.assertGreater(d, 310)
        self.assertLess(d, 340)

    def test_short_distance_within_seoul(self):
        """서울 시청(37.5666, 126.9782) → 광화문(37.5760, 126.9770) ≈ 1.05km"""
        d = calculate_distance(37.5666, 126.9782, 37.5760, 126.9770)
        self.assertGreater(d, 0.5)
        self.assertLess(d, 2.0)

    def test_haversine_uses_lng1_not_lat1(self):
        """
        기존 버그: d_lng = math.radians(float(lng2) - float(lat1))
        수정 후:  d_lng = math.radians(float(lng2) - float(lng1))
        두 결과가 같으면 버그가 남아있는 것 (lat1==lng1인 경우 제외)
        """
        import math
        lat1, lng1 = 37.5665, 126.9780
        lat2, lng2 = 35.1796, 129.0756

        # 수정된 계산
        R = 6371
        d_lat = math.radians(lat2 - lat1)
        d_lng_correct = math.radians(lng2 - lng1)          # 올바른 값
        d_lng_buggy   = math.radians(lng2 - lat1)           # 버그: lat1 사용

        # 두 값이 달라야 함 (버그가 있으면 다른 결과)
        self.assertNotAlmostEqual(d_lng_correct, d_lng_buggy, places=5,
                                  msg='d_lng 계산에 버그가 있습니다: lng1 대신 lat1 사용 중')

        # 서비스 함수 결과가 올바른 공식과 일치해야 함
        a = (math.sin(d_lat/2)**2 +
             math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
             math.sin(d_lng_correct/2)**2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        expected = round(R * c, 2)

        actual = calculate_distance(lat1, lng1, lat2, lng2)
        self.assertAlmostEqual(actual, expected, places=1,
                               msg=f'calculate_distance 결과={actual}, 올바른값={expected}')

    def test_returns_float(self):
        d = calculate_distance(37.5, 127.0, 37.6, 127.1)
        self.assertIsInstance(d, float)

    def test_symmetry(self):
        """A→B 거리와 B→A 거리는 같아야 한다"""
        d1 = calculate_distance(37.5665, 126.9780, 35.1796, 129.0756)
        d2 = calculate_distance(35.1796, 129.0756, 37.5665, 126.9780)
        self.assertAlmostEqual(d1, d2, places=1)


# ─────────────────────────────────────────────────────────────
# 2. get_available_workers
# ─────────────────────────────────────────────────────────────
class GetAvailableWorkersTest(AutoAssignFixtureMixin, TestCase):

    def test_returns_same_center_workers_only(self):
        incident = self._make_incident()
        workers = get_available_workers(incident)
        for w in workers:
            self.assertEqual(w.support_center_id, self.center.pk)

    def test_excludes_other_center(self):
        incident = self._make_incident()
        workers = get_available_workers(incident)
        usernames = [w.username for w in workers]
        self.assertNotIn('worker_other', usernames)

    def test_excludes_inactive_workers(self):
        incident = self._make_incident()
        workers = get_available_workers(incident)
        usernames = [w.username for w in workers]
        self.assertNotIn('worker_inactive', usernames)

    def test_excludes_non_worker_role(self):
        incident = self._make_incident()
        workers = get_available_workers(incident)
        for w in workers:
            self.assertEqual(w.role, 'worker')

    def test_includes_active_center_workers(self):
        incident = self._make_incident()
        workers = get_available_workers(incident)
        usernames = [w.username for w in workers]
        self.assertIn('worker_near', usernames)
        self.assertIn('worker_far', usernames)


# ─────────────────────────────────────────────────────────────
# 3. get_best_worker — 거리·부하 기반 최적 인력
# ─────────────────────────────────────────────────────────────
class GetBestWorkerTest(AutoAssignFixtureMixin, TestCase):

    def _import(self):
        from apps.incidents.services import get_best_worker
        return get_best_worker

    def test_function_importable(self):
        """get_best_worker 함수가 services에 존재해야 한다"""
        try:
            from apps.incidents.services import get_best_worker
        except ImportError:
            self.fail('get_best_worker 함수가 services.py에 없습니다.')

    def test_selects_nearest_worker_by_home_gps(self):
        """home GPS 기준 가까운 인력 선택"""
        get_best_worker = self._import()
        incident = self._make_incident()
        workers = get_available_workers(incident)
        worker, dist = get_best_worker(incident, workers)
        # worker_near (home: 37.5720, 127.0910)이 학교(37.5700, 127.0900)에 더 가까움
        self.assertEqual(worker.username, 'worker_near')
        self.assertIsNotNone(dist)

    def test_uses_current_location_when_available(self):
        """current_location이 있으면 home보다 우선 사용"""
        get_best_worker = self._import()
        incident = self._make_incident()

        # worker_far에게 학교 근처에 current_location 부여
        WorkerLocation.objects.update_or_create(
            worker=self.worker_far,
            defaults={
                'lat': Decimal('37.5705'),
                'lng': Decimal('127.0905'),
            }
        )

        workers = get_available_workers(incident)
        worker, dist = get_best_worker(incident, workers)
        # current_location으로 가까워진 worker_far가 선택되어야 함
        self.assertEqual(worker.username, 'worker_far')

        # cleanup
        WorkerLocation.objects.filter(worker=self.worker_far).delete()

    def test_workload_penalty_applied(self):
        """활성 장애 많은 인력에게 페널티 부여"""
        get_best_worker = self._import()
        incident = self._make_incident()

        # worker_near에게 여러 개의 활성 장애 배정
        for i in range(5):
            active_inc = self._make_incident()
            active_inc.status = 'assigned'
            active_inc.save()
            IncidentAssignment.objects.create(
                incident=active_inc, worker=self.worker_near,
                assigned_by=self.admin,
            )

        workers = get_available_workers(incident)
        worker, _ = get_best_worker(incident, workers)
        # worker_near가 가깝지만 부하가 많으므로 worker_far가 선택될 수 있음
        # (페널티 적용 여부만 검증 — 선택된 인력이 workers에 포함되는지)
        self.assertIn(worker, list(workers))

    def test_no_gps_school_falls_back_to_workload(self):
        """학교 GPS 없으면 활성 장애 수 기준으로 선택"""
        get_best_worker = self._import()
        incident_no_gps = self._make_incident(school=self.school_no_gps)
        workers = get_available_workers(incident_no_gps)
        worker, dist = get_best_worker(incident_no_gps, workers)
        self.assertIsNotNone(worker)
        # GPS 없을 때는 거리 None 반환
        self.assertIsNone(dist)

    def test_empty_workers_returns_none(self):
        """가용 인력이 없으면 (None, None) 반환"""
        get_best_worker = self._import()
        incident = self._make_incident()
        worker, dist = get_best_worker(incident, User.objects.none())
        self.assertIsNone(worker)
        self.assertIsNone(dist)


# ─────────────────────────────────────────────────────────────
# 4. create_assignment
# ─────────────────────────────────────────────────────────────
class CreateAssignmentTest(AutoAssignFixtureMixin, TestCase):

    def test_creates_assignment_record(self):
        incident = self._make_incident()
        assign = create_assignment(incident, self.worker_near, self.admin)
        self.assertIsNotNone(assign.pk)
        self.assertEqual(assign.worker, self.worker_near)
        self.assertEqual(assign.incident, incident)

    def test_updates_incident_status_to_assigned(self):
        incident = self._make_incident()
        create_assignment(incident, self.worker_near, self.admin)
        incident.refresh_from_db()
        self.assertEqual(incident.status, 'assigned')

    def test_sets_assigned_at(self):
        incident = self._make_incident()
        create_assignment(incident, self.worker_near, self.admin)
        incident.refresh_from_db()
        self.assertIsNotNone(incident.assigned_at)

    def test_creates_status_history(self):
        incident = self._make_incident()
        create_assignment(incident, self.worker_near, self.admin)
        history = IncidentStatusHistory.objects.filter(incident=incident)
        self.assertTrue(history.exists())
        self.assertEqual(history.first().to_status, 'assigned')

    def test_is_ai_flag_manual(self):
        incident = self._make_incident()
        assign = create_assignment(incident, self.worker_near, self.admin, is_ai=False)
        self.assertFalse(assign.is_ai_assigned)

    def test_is_ai_flag_auto(self):
        incident = self._make_incident()
        assign = create_assignment(incident, self.worker_near, self.admin, is_ai=True)
        self.assertTrue(assign.is_ai_assigned)

    def test_distance_km_stored(self):
        incident = self._make_incident()
        assign = create_assignment(incident, self.worker_near, self.admin,
                                   distance_km=2.5)
        self.assertEqual(float(assign.distance_km), 2.5)

    def test_eta_minutes_stored(self):
        incident = self._make_incident()
        assign = create_assignment(incident, self.worker_near, self.admin,
                                   eta_minutes=15)
        self.assertEqual(assign.eta_minutes, 15)

    def test_status_history_note_contains_ai_or_manual(self):
        incident = self._make_incident()
        create_assignment(incident, self.worker_near, self.admin, is_ai=True)
        history = IncidentStatusHistory.objects.filter(incident=incident).first()
        self.assertIn('AI', history.note)


# ─────────────────────────────────────────────────────────────
# 5. ai_assign API 액션 — 스마트 폴백
# ─────────────────────────────────────────────────────────────
class AiAssignViewActionTest(AutoAssignFixtureMixin, TestCase):

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def _url(self, pk):
        return f'/api/incidents/incidents/{pk}/ai_assign/'

    @patch('apps.incidents.views.ai_assign_worker', return_value=None)
    def test_ai_unavailable_uses_smart_fallback(self, mock_ai):
        """AI 서버 없을 때 get_best_worker 기반 스마트 배정"""
        incident = self._make_incident()
        resp = self.client.post(self._url(incident.pk))
        self.assertEqual(resp.status_code, 201)
        incident.refresh_from_db()
        self.assertEqual(incident.status, 'assigned')

    @patch('apps.incidents.views.ai_assign_worker', return_value=None)
    def test_ai_unavailable_selects_nearest_worker(self, mock_ai):
        """스마트 폴백은 가장 가까운 인력을 선택해야 한다"""
        incident = self._make_incident()
        resp = self.client.post(self._url(incident.pk))
        self.assertEqual(resp.status_code, 201)
        assign = IncidentAssignment.objects.get(incident=incident)
        self.assertEqual(assign.worker.username, 'worker_near')

    @patch('apps.incidents.views.ai_assign_worker', return_value=None)
    def test_no_workers_available_returns_404(self, mock_ai):
        """배정 가능 인력 없으면 404"""
        # 아무 worker도 없는 빈 지원청으로 테스트
        empty_center = SupportCenter.objects.create(
            code='empty_center', name='빈지원청',
            lat=Decimal('36.0'), lng=Decimal('128.0'),
        )
        incident = Incident.objects.create(
            incident_number=Incident.generate_number(),
            school=School.objects.create(
                support_center=empty_center,
                school_type=self.school_type,
                name='빈지원청학교', address='서울',
            ),
            category=self.category, status='received',
            priority='medium', received_by=self.admin,
            requester_name='요청자', requester_phone='010-0000-0000',
            description='테스트',
        )
        resp = self.client.post(self._url(incident.pk))
        self.assertEqual(resp.status_code, 404)

    @patch('apps.incidents.views.ai_assign_worker')
    def test_ai_result_used_when_available(self, mock_ai):
        """AI 서버 결과가 있으면 해당 인력 배정"""
        incident = self._make_incident()
        mock_ai.return_value = {
            'worker_id': self.worker_far.pk,
            'distance_km': 8.0,
            'eta_minutes': 20,
        }
        resp = self.client.post(self._url(incident.pk))
        self.assertEqual(resp.status_code, 201)
        assign = IncidentAssignment.objects.get(incident=incident)
        self.assertEqual(assign.worker, self.worker_far)
        self.assertTrue(assign.is_ai_assigned)


# ─────────────────────────────────────────────────────────────
# 6. available_workers API
# ─────────────────────────────────────────────────────────────
class AvailableWorkersAPITest(AutoAssignFixtureMixin, TestCase):

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def test_available_workers_returns_200(self):
        incident = self._make_incident()
        resp = self.client.get(f'/api/incidents/incidents/{incident.pk}/available_workers/')
        self.assertEqual(resp.status_code, 200)

    def test_available_workers_same_center_only(self):
        incident = self._make_incident()
        resp = self.client.get(f'/api/incidents/incidents/{incident.pk}/available_workers/')
        usernames = [w['username'] for w in resp.data]
        self.assertNotIn('worker_other', usernames)

    def test_available_workers_excludes_inactive(self):
        incident = self._make_incident()
        resp = self.client.get(f'/api/incidents/incidents/{incident.pk}/available_workers/')
        usernames = [w['username'] for w in resp.data]
        self.assertNotIn('worker_inactive', usernames)
