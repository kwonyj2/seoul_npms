"""
Phase 4-2: WBS 완성 테스트

테스트 범위:
  1. WBSItem 모델 — CRUD, 계층구조, recalculate_from_children
  2. WBSItemSerializer — 필드, read_only, has_children
  3. WBSItemViewSet — CRUD + 필터(project/phase/depth)
  4. gantt 액션 — 포맷 검증
  5. summary 액션 — 페이즈별 계획/실적/준수율 계산
  6. update_progress 액션 — 수동 소스만 허용, 유효성 검사, 버블업
  7. _bubble_up 시그널 — 부모 재계산 전파
  8. 산출물 시그널 — ArtifactFile 생성 → WBS 100%
  9. 점검 시그널 — InspectionPlan 저장 → WBS 갱신
"""
from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.audit.models import AuditProject, ArtifactTemplate, ArtifactFile
from apps.progress.models import InspectionPlan
from apps.wbs.models import WBSItem
from apps.wbs.serializers import WBSItemSerializer


# ─────────────────────────────────────────────────────────────
# 공통 픽스처 믹스인
# ─────────────────────────────────────────────────────────────
class WBSFixtureMixin:
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            username='wbs_admin', email='wbs_admin@test.com',
            password='pass', role='admin',
        )
        cls.project = AuditProject.objects.create(
            name='2026 NPMS 감리', year=2026,
        )
        # 깊이 1 (대항목)
        cls.item_root = WBSItem.objects.create(
            project=cls.project, code='1', depth=1,
            phase='plan', seq=1, name='계획 단계',
            weight=Decimal('0.2000'), progress_source='children',
        )
        # 깊이 2 (중항목)
        cls.item_mid = WBSItem.objects.create(
            project=cls.project, code='1.1', depth=2,
            phase='plan', seq=2, name='착수 준비',
            parent=cls.item_root,
            weight=Decimal('0.1000'), progress_source='children',
        )
        # 깊이 3 (소항목, 수동 소스)
        cls.item_leaf1 = WBSItem.objects.create(
            project=cls.project, code='1.1.1', depth=3,
            phase='plan', seq=3, name='착수 회의',
            parent=cls.item_mid,
            weight=Decimal('0.0500'), progress_source='manual',
            planned_start=date(2026, 1, 1), planned_end=date(2026, 1, 31),
        )
        cls.item_leaf2 = WBSItem.objects.create(
            project=cls.project, code='1.1.2', depth=3,
            phase='plan', seq=4, name='착수 보고서',
            parent=cls.item_mid,
            weight=Decimal('0.0500'), progress_source='manual',
            planned_start=date(2026, 1, 1), planned_end=date(2026, 3, 31),
        )


# ─────────────────────────────────────────────────────────────
# 1. WBSItem 모델
# ─────────────────────────────────────────────────────────────
class WBSItemModelTest(WBSFixtureMixin, TestCase):

    def test_str_representation(self):
        self.assertEqual(str(self.item_root), '[1] 계획 단계')

    def test_unique_together_project_code(self):
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            WBSItem.objects.create(
                project=self.project, code='1', depth=1,
                phase='plan', seq=99, name='중복코드',
                weight=Decimal('0'), progress_source='manual',
            )

    def test_parent_child_relationship(self):
        self.assertEqual(self.item_leaf1.parent, self.item_mid)
        self.assertIn(self.item_leaf1, self.item_mid.children.all())

    def test_recalculate_from_children_weighted_average(self):
        """가중 평균: leaf1=100%(0.05), leaf2=0%(0.05) → 50%"""
        self.item_leaf1.progress = 100
        self.item_leaf1.save(update_fields=['progress'])
        self.item_leaf2.progress = 0
        self.item_leaf2.save(update_fields=['progress'])
        self.item_mid.recalculate_from_children()
        self.item_mid.refresh_from_db()
        self.assertEqual(self.item_mid.progress, 50)

    def test_recalculate_weighted_uneven(self):
        """가중치 불균등: leaf1=weight 0.06, leaf2=weight 0.04, leaf1=100%, leaf2=50%"""
        leaf1 = WBSItem.objects.create(
            project=self.project, code='1.2.1', depth=3,
            phase='plan', seq=10, name='leaf_a',
            parent=self.item_mid,
            weight=Decimal('0.0600'), progress_source='manual', progress=100,
        )
        leaf2 = WBSItem.objects.create(
            project=self.project, code='1.2.2', depth=3,
            phase='plan', seq=11, name='leaf_b',
            parent=self.item_mid,
            weight=Decimal('0.0400'), progress_source='manual', progress=50,
        )
        # 임시 parent (item_mid는 leaf1/2도 포함) — 별도 parent 생성
        mid2 = WBSItem.objects.create(
            project=self.project, code='2.1', depth=2,
            phase='execute', seq=20, name='수행중항목',
            weight=Decimal('0.1'), progress_source='children',
        )
        leaf1.parent = mid2
        leaf1.save()
        leaf2.parent = mid2
        leaf2.save()
        mid2.recalculate_from_children()
        mid2.refresh_from_db()
        # (0.06*100 + 0.04*50) / 0.10 = 80
        self.assertEqual(mid2.progress, 80)

    def test_recalculate_no_children_returns_silently(self):
        """하위 없는 항목은 recalculate 호출해도 오류 없음"""
        solo = WBSItem.objects.create(
            project=self.project, code='9.9.9', depth=3,
            phase='close', seq=99, name='단독항목',
            weight=Decimal('0'), progress_source='children',
        )
        solo.recalculate_from_children()  # 예외 없어야 함

    def test_recalculate_zero_total_weight_returns_silently(self):
        """총 가중치 0인 경우 silently return"""
        parent = WBSItem.objects.create(
            project=self.project, code='8.1', depth=2,
            phase='close', seq=98, name='제로가중합',
            weight=Decimal('0'), progress_source='children',
        )
        WBSItem.objects.create(
            project=self.project, code='8.1.1', depth=3,
            phase='close', seq=98, name='영가중치자식',
            parent=parent, weight=Decimal('0'), progress_source='manual',
        )
        parent.recalculate_from_children()  # 예외 없어야 함

    def test_is_milestone_field(self):
        ms = WBSItem.objects.create(
            project=self.project, code='M1', depth=1,
            phase='execute', seq=50, name='착수감리',
            weight=Decimal('0'), progress_source='manual', is_milestone=True,
        )
        self.assertTrue(ms.is_milestone)


# ─────────────────────────────────────────────────────────────
# 2. WBSItemSerializer
# ─────────────────────────────────────────────────────────────
class WBSItemSerializerTest(WBSFixtureMixin, TestCase):

    def test_serializer_contains_required_fields(self):
        s = WBSItemSerializer(self.item_root)
        for key in ('id', 'code', 'depth', 'name', 'phase', 'progress',
                    'weight', 'has_children', 'phase_display',
                    'progress_source_display'):
            self.assertIn(key, s.data)

    def test_has_children_true_for_parent(self):
        s = WBSItemSerializer(self.item_mid)
        self.assertTrue(s.data['has_children'])

    def test_has_children_false_for_leaf(self):
        s = WBSItemSerializer(self.item_leaf1)
        self.assertFalse(s.data['has_children'])

    def test_phase_display_korean(self):
        s = WBSItemSerializer(self.item_root)
        self.assertEqual(s.data['phase_display'], '계획')

    def test_updated_at_read_only(self):
        s = WBSItemSerializer(self.item_root)
        self.assertIn('updated_at', s.data)

    def test_assignee_name_empty_when_no_assignee(self):
        s = WBSItemSerializer(self.item_leaf1)
        self.assertEqual(s.data['assignee_name'], '')


# ─────────────────────────────────────────────────────────────
# 3. WBSItemViewSet — CRUD + 필터
# ─────────────────────────────────────────────────────────────
class WBSItemViewSetTest(WBSFixtureMixin, TestCase):

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        self.base_url = '/api/wbs/items/'

    def test_list_returns_200(self):
        resp = self.client.get(self.base_url)
        self.assertEqual(resp.status_code, 200)

    def test_list_filter_by_project(self):
        resp = self.client.get(f'{self.base_url}?project={self.project.pk}')
        self.assertEqual(resp.status_code, 200)
        codes = [i['code'] for i in resp.data]
        self.assertIn('1', codes)

    def test_list_filter_by_phase(self):
        resp = self.client.get(f'{self.base_url}?project={self.project.pk}&phase=plan')
        for item in resp.data:
            self.assertEqual(item['phase'], 'plan')

    def test_list_filter_by_depth(self):
        resp = self.client.get(f'{self.base_url}?project={self.project.pk}&depth=3')
        for item in resp.data:
            self.assertEqual(item['depth'], 3)

    def test_retrieve_single_item(self):
        resp = self.client.get(f'{self.base_url}{self.item_leaf1.pk}/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['code'], '1.1.1')

    def test_create_item(self):
        resp = self.client.post(self.base_url, {
            'project': self.project.pk,
            'code': '3.1.1', 'depth': 3, 'phase': 'close',
            'seq': 100, 'name': '신규 항목', 'weight': '0.0100',
            'progress_source': 'manual',
        }, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data['name'], '신규 항목')

    def test_update_item_name(self):
        resp = self.client.patch(
            f'{self.base_url}{self.item_leaf1.pk}/',
            {'name': '이름 수정'}, format='json'
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['name'], '이름 수정')

    def test_delete_item(self):
        to_del = WBSItem.objects.create(
            project=self.project, code='DEL.1', depth=1,
            phase='plan', seq=999, name='삭제용',
            weight=Decimal('0'), progress_source='manual',
        )
        resp = self.client.delete(f'{self.base_url}{to_del.pk}/')
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(WBSItem.objects.filter(pk=to_del.pk).exists())

    def test_unauthenticated_returns_401(self):
        anon = APIClient()
        resp = anon.get(self.base_url)
        self.assertIn(resp.status_code, [401, 403])


# ─────────────────────────────────────────────────────────────
# 4. gantt 액션
# ─────────────────────────────────────────────────────────────
class WBSGanttActionTest(WBSFixtureMixin, TestCase):

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def test_gantt_requires_project_param(self):
        resp = self.client.get('/api/wbs/items/gantt/')
        self.assertEqual(resp.status_code, 400)

    def test_gantt_returns_list(self):
        resp = self.client.get(f'/api/wbs/items/gantt/?project={self.project.pk}')
        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(resp.data, list)

    def test_gantt_item_has_required_keys(self):
        resp = self.client.get(f'/api/wbs/items/gantt/?project={self.project.pk}')
        if resp.data:
            item = resp.data[0]
            for k in ('id', 'code', 'text', 'depth', 'progress', 'is_milestone'):
                self.assertIn(k, item)

    def test_gantt_progress_is_fractional(self):
        """progress 필드는 0~1 사이 소수 (0~100% → /100)"""
        self.item_leaf1.progress = 50
        self.item_leaf1.save()
        resp = self.client.get(f'/api/wbs/items/gantt/?project={self.project.pk}')
        items = {i['id']: i for i in resp.data}
        self.assertAlmostEqual(items[self.item_leaf1.pk]['progress'], 0.5)

    def test_gantt_date_format(self):
        """날짜는 YYYY-MM-DD 포맷"""
        resp = self.client.get(f'/api/wbs/items/gantt/?project={self.project.pk}')
        items = {i['id']: i for i in resp.data}
        start = items[self.item_leaf1.pk]['start_date']
        self.assertRegex(start, r'^\d{4}-\d{2}-\d{2}$')

    def test_gantt_null_dates_returned_as_none(self):
        """날짜 없는 항목은 None 반환"""
        resp = self.client.get(f'/api/wbs/items/gantt/?project={self.project.pk}')
        items = {i['id']: i for i in resp.data}
        # item_root는 planned_start 없음
        self.assertIsNone(items[self.item_root.pk]['start_date'])


# ─────────────────────────────────────────────────────────────
# 5. summary 액션
# ─────────────────────────────────────────────────────────────
class WBSSummaryActionTest(WBSFixtureMixin, TestCase):

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def test_summary_requires_project_param(self):
        resp = self.client.get('/api/wbs/items/summary/')
        self.assertEqual(resp.status_code, 400)

    def test_summary_returns_list_with_total(self):
        resp = self.client.get(f'/api/wbs/items/summary/?project={self.project.pk}')
        self.assertEqual(resp.status_code, 200)
        phases = [r['phase'] for r in resp.data]
        self.assertIn('total', phases)
        self.assertIn('plan', phases)

    def test_summary_has_required_keys(self):
        resp = self.client.get(f'/api/wbs/items/summary/?project={self.project.pk}')
        for row in resp.data:
            for k in ('phase', 'phase_display', 'planned_progress',
                      'actual_progress', 'compliance_rate', 'total_weight'):
                self.assertIn(k, row)

    def test_summary_actual_progress_reflects_progress(self):
        """실적 진척률은 WBSItem.progress 값의 가중 평균이어야 한다"""
        # leaf1, leaf2 모두 100% 처리 (children 소스 제외)
        self.item_leaf1.progress = 100
        self.item_leaf1.save()
        self.item_leaf2.progress = 100
        self.item_leaf2.save()
        resp = self.client.get(f'/api/wbs/items/summary/?project={self.project.pk}')
        plan_row = next(r for r in resp.data if r['phase'] == 'plan')
        # leaf1+leaf2 weight 합=0.10, total leaf weight = 0.10 → 100%
        self.assertEqual(plan_row['actual_progress'], 100.0)

    def test_summary_compliance_zero_when_no_plan(self):
        """계획진척이 0이면 공정준수율도 0"""
        resp = self.client.get(f'/api/wbs/items/summary/?project={self.project.pk}')
        for row in resp.data:
            if row['planned_progress'] == 0:
                self.assertEqual(row['compliance_rate'], 0)


# ─────────────────────────────────────────────────────────────
# 6. update_progress 액션
# ─────────────────────────────────────────────────────────────
class WBSUpdateProgressActionTest(WBSFixtureMixin, TestCase):

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def _url(self, pk):
        return f'/api/wbs/items/{pk}/progress/'

    def test_manual_source_can_update(self):
        resp = self.client.patch(self._url(self.item_leaf1.pk),
                                 {'progress': 60}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.item_leaf1.refresh_from_db()
        self.assertEqual(self.item_leaf1.progress, 60)

    def test_non_manual_source_returns_400(self):
        """children 소스 항목에는 수동 업데이트 불가"""
        resp = self.client.patch(self._url(self.item_root.pk),
                                 {'progress': 50}, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('error', resp.data)

    def test_missing_progress_value_returns_400(self):
        resp = self.client.patch(self._url(self.item_leaf1.pk),
                                 {}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_progress_out_of_range_returns_400(self):
        resp = self.client.patch(self._url(self.item_leaf1.pk),
                                 {'progress': 150}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_progress_negative_returns_400(self):
        resp = self.client.patch(self._url(self.item_leaf1.pk),
                                 {'progress': -1}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_non_numeric_progress_returns_400(self):
        """비숫자 progress 값은 400을 반환해야 한다 (ValueError 아님)"""
        resp = self.client.patch(self._url(self.item_leaf1.pk),
                                 {'progress': 'abc'}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_update_also_saves_weekly_fields(self):
        resp = self.client.patch(self._url(self.item_leaf1.pk), {
            'progress': 40,
            'this_week_plan': '회의 준비',
            'this_week_actual': '자료 수집',
            'next_week_plan': '보고서 작성',
        }, format='json')
        self.assertEqual(resp.status_code, 200)
        self.item_leaf1.refresh_from_db()
        self.assertEqual(self.item_leaf1.this_week_plan, '회의 준비')

    def test_update_triggers_bubble_up(self):
        """진척 업데이트 후 부모(children 소스)가 재계산 되어야 한다"""
        # item_leaf1, item_leaf2 각각 weight=0.05씩
        self.item_leaf2.progress = 0
        self.item_leaf2.save()
        # leaf1을 100%로 업데이트
        self.client.patch(self._url(self.item_leaf1.pk),
                          {'progress': 100}, format='json')
        self.item_mid.refresh_from_db()
        # item_mid는 children 소스: (100*0.05 + 0*0.05) / 0.10 = 50
        self.assertEqual(self.item_mid.progress, 50)

    def test_update_progress_boundary_zero(self):
        resp = self.client.patch(self._url(self.item_leaf1.pk),
                                 {'progress': 0}, format='json')
        self.assertEqual(resp.status_code, 200)

    def test_update_progress_boundary_hundred(self):
        resp = self.client.patch(self._url(self.item_leaf1.pk),
                                 {'progress': 100}, format='json')
        self.assertEqual(resp.status_code, 200)


# ─────────────────────────────────────────────────────────────
# 7. _bubble_up 시그널
# ─────────────────────────────────────────────────────────────
class BubbleUpTest(WBSFixtureMixin, TestCase):

    def test_bubble_up_recalculates_parent_chain(self):
        """리프 → 중간 → 루트 순서로 재계산 전파"""
        from apps.wbs.signals import _bubble_up
        self.item_leaf1.progress = 80
        self.item_leaf1.save()
        self.item_leaf2.progress = 40
        self.item_leaf2.save()

        _bubble_up(self.item_leaf1)
        self.item_mid.refresh_from_db()
        # (80*0.05 + 40*0.05) / 0.10 = 60
        self.assertEqual(self.item_mid.progress, 60)

    def test_bubble_up_skips_non_children_source(self):
        """children 소스가 아닌 부모는 재계산 안 함"""
        from apps.wbs.signals import _bubble_up
        # item_mid 를 children → manual 로 변경
        self.item_mid.progress_source = 'manual'
        self.item_mid.progress = 99
        self.item_mid.save()

        _bubble_up(self.item_leaf1)
        self.item_mid.refresh_from_db()
        # manual 소스라 재계산 건너뜀 → 여전히 99
        self.assertEqual(self.item_mid.progress, 99)

    def test_bubble_up_with_no_parent(self):
        """부모 없는 루트 노드에서 _bubble_up 은 오류 없이 종료"""
        from apps.wbs.signals import _bubble_up
        _bubble_up(self.item_root)   # 예외 없어야 함


# ─────────────────────────────────────────────────────────────
# 8. 산출물 시그널 — ArtifactFile 저장 → WBS 100%
# ─────────────────────────────────────────────────────────────
class ArtifactFileSignalTest(WBSFixtureMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.template = ArtifactTemplate.objects.create(
            project=cls.project,
            audit_phase='initiation',
            submit_timing='on_completion',
            name='착수 보고서 템플릿',
            code='SEN-PM-001',
        )
        # artifact 소스로 연결된 WBSItem
        cls.artifact_item = WBSItem.objects.create(
            project=cls.project, code='2.1.1', depth=3,
            phase='plan', seq=30, name='착수보고서 WBS',
            weight=Decimal('0.05'), progress_source='artifact',
            linked_template=cls.template,
        )

    def test_artifact_file_creation_sets_progress_100(self):
        af = ArtifactFile.objects.create(
            project=self.project,
            template=self.template,
            file_name='SEN-PM-001_착수보고서_20260115.pdf',
        )
        self.artifact_item.refresh_from_db()
        self.assertEqual(self.artifact_item.progress, 100)

    def test_artifact_file_without_template_no_effect(self):
        """template 없는 파일은 WBS에 영향 없음"""
        initial = self.artifact_item.progress
        ArtifactFile.objects.create(
            project=self.project,
            template=None,
            file_name='no_template.pdf',
        )
        self.artifact_item.refresh_from_db()
        self.assertEqual(self.artifact_item.progress, initial)


# ─────────────────────────────────────────────────────────────
# 9. 점검 시그널 — InspectionPlan 저장 → WBS 갱신
# ─────────────────────────────────────────────────────────────
class InspectionSignalTest(WBSFixtureMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.plan = InspectionPlan.objects.create(
            name='2026 1분기 점검',
            year=2026, quarter=1,
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 31),
            created_by=cls.admin,
        )
        cls.inspection_item = WBSItem.objects.create(
            project=cls.project, code='3.1.1', depth=3,
            phase='execute', seq=40, name='점검 진행 WBS',
            weight=Decimal('0.05'), progress_source='inspection',
            linked_inspection=cls.plan,
        )

    def test_inspection_plan_save_updates_wbs(self):
        """InspectionPlan 저장 시 연결된 WBSItem 진척이 갱신되어야 한다"""
        # InspectionPlan에 SchoolInspection이 없으면 progress_pct=0
        # 강제로 progress_pct를 mock 하거나 signal을 직접 호출
        from apps.wbs.signals import sync_inspection_plan
        # signal 직접 발화 (save 없이)
        # plan.progress_pct = 0 (school_inspections 없으므로)
        # 그냥 save 로 signal 발화
        self.plan.description = '갱신 테스트'
        self.plan.save()
        self.inspection_item.refresh_from_db()
        # progress_pct는 0 (school_inspections 없음) → WBS도 0
        self.assertEqual(self.inspection_item.progress, 0)

    def test_inspection_signal_sets_correct_progress(self):
        """signal 직접 호출로 진척 갱신 확인"""
        from apps.wbs.signals import sync_inspection_plan
        from unittest.mock import patch, PropertyMock
        # progress_pct를 60으로 mock
        with patch.object(
            type(self.plan), 'progress_pct',
            new_callable=PropertyMock, return_value=60
        ):
            sync_inspection_plan(
                sender=type(self.plan), instance=self.plan, created=False
            )
        self.inspection_item.refresh_from_db()
        self.assertEqual(self.inspection_item.progress, 60)
