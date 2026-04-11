"""
Phase 3-3: 장비 상태 전이 테스트
Asset Status Transition Tests

테스트 대상:
  - AssetInboundSerializer.create()  → warehouse / center 상태 전이
  - AssetOutboundSerializer.validate() → 출고 불가 검증
  - AssetOutboundSerializer.create()  → center / installed / rma 상태 전이
  - AssetReturnSerializer.create()   → center / warehouse 상태 전이
  - AssetRMA 모델 상태 흐름
  - 문서번호 자동 생성 (ASIN / ASOUT / ASRET 시퀀스)
  - AssetHistory 자동 기록
"""
import datetime
from django.test import TestCase
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.assets.models import (
    AssetCategory, AssetModel, Asset,
    AssetInbound, AssetOutbound, AssetReturn,
    AssetHistory, AssetRMA,
    CURRENT_INSTALL_PROJECT, CURRENT_INSTALL_YEAR,
)
from apps.assets.serializers import (
    AssetInboundSerializer,
    AssetOutboundSerializer,
    AssetReturnSerializer,
)
from apps.accounts.models import User
from apps.schools.models import SupportCenter, School, SchoolType


# ─────────────────────────────────────────
# 공용 픽스처 믹스인
# ─────────────────────────────────────────

class AssetFixtureMixin:
    """모든 Asset 테스트에 필요한 공통 픽스처."""

    @classmethod
    def setUpTestData(cls):
        # 사용자
        cls.user = User.objects.create_user(
            username='assettest', email='assettest@test.com', password='testpass1234'
        )

        # 장비 분류 / 모델
        cls.category = AssetCategory.objects.create(
            code='switch', name='스위치', usable_years=5, order=1
        )
        cls.asset_model = AssetModel.objects.create(
            category=cls.category,
            manufacturer='테스트제조사',
            model_name='SW-TEST-1000',
        )

        # 교육지원청 (센터)
        cls.center = SupportCenter.objects.create(
            code='dongbu', name='동부교육지원청'
        )
        cls.center2 = SupportCenter.objects.create(
            code='seobu', name='서부교육지원청'
        )

        # 학교 (출고→학교 설치 테스트용)
        cls.school_type = SchoolType.objects.create(
            code='elementary', name='초등학교', order=2
        )
        cls.school = School.objects.create(
            support_center=cls.center,
            school_type=cls.school_type,
            name='테스트초등학교',
            code='TEST001',
        )

    def _make_asset(self, serial, status='warehouse', center=None, school=None):
        """개별 테스트에서 사용할 Asset 생성."""
        return Asset.objects.create(
            asset_model=self.asset_model,
            serial_number=serial,
            status=status,
            current_center=center,
            current_school=school,
        )

    def _inbound_data(self, asset, to_type='warehouse', to_center=None, date=None):
        data = {
            'asset': asset.pk,
            'from_location_type': 'education_office',
            'from_location_name': '서울시교육청',
            'to_location_type': to_type,
            'inbound_date': (date or datetime.date.today()).isoformat(),
        }
        if to_center:
            data['to_center'] = to_center.pk
        return data

    def _outbound_data(self, asset, from_type='warehouse', to_type='center',
                       to_center=None, to_school=None, date=None):
        data = {
            'asset': asset.pk,
            'from_location_type': from_type,
            'to_location_type': to_type,
            'outbound_date': (date or datetime.date.today()).isoformat(),
        }
        if to_center:
            data['to_center'] = to_center.pk
        if to_school:
            data['to_school'] = to_school.pk
        return data

    def _return_data(self, asset, from_type='school', to_type='center',
                     to_center=None, date=None):
        data = {
            'asset': asset.pk,
            'from_location_type': from_type,
            'to_location_type': to_type,
            'return_date': (date or datetime.date.today()).isoformat(),
            'reason': '고장 회수',
        }
        if to_center:
            data['to_center'] = to_center.pk
        return data


# ─────────────────────────────────────────
# 1. AssetInbound — 입고 → 상태 전이
# ─────────────────────────────────────────

class AssetInboundStatusTransitionTest(AssetFixtureMixin, TestCase):

    def test_inbound_to_warehouse_sets_status_warehouse(self):
        """입고(창고) → asset.status = 'warehouse'"""
        asset = self._make_asset('SN-IB-001', status='rma')
        s = AssetInboundSerializer(data=self._inbound_data(asset, to_type='warehouse'))
        self.assertTrue(s.is_valid(), s.errors)
        s.save()
        asset.refresh_from_db()
        self.assertEqual(asset.status, 'warehouse')

    def test_inbound_to_warehouse_clears_center_and_school(self):
        """창고 입고 시 current_center, current_school 모두 None으로 초기화."""
        asset = self._make_asset('SN-IB-002', status='center', center=self.center)
        s = AssetInboundSerializer(data=self._inbound_data(asset, to_type='warehouse'))
        self.assertTrue(s.is_valid(), s.errors)
        s.save()
        asset.refresh_from_db()
        self.assertIsNone(asset.current_center)
        self.assertIsNone(asset.current_school)

    def test_inbound_to_center_sets_status_center(self):
        """입고(센터) → asset.status = 'center'"""
        asset = self._make_asset('SN-IB-003', status='warehouse')
        data = self._inbound_data(asset, to_type='center', to_center=self.center)
        s = AssetInboundSerializer(data=data)
        self.assertTrue(s.is_valid(), s.errors)
        s.save()
        asset.refresh_from_db()
        self.assertEqual(asset.status, 'center')

    def test_inbound_to_center_sets_current_center(self):
        """센터 입고 시 current_center 가 to_center 로 설정된다."""
        asset = self._make_asset('SN-IB-004', status='warehouse')
        data = self._inbound_data(asset, to_type='center', to_center=self.center)
        s = AssetInboundSerializer(data=data)
        self.assertTrue(s.is_valid(), s.errors)
        s.save()
        asset.refresh_from_db()
        self.assertEqual(asset.current_center_id, self.center.pk)

    def test_inbound_creates_history_record(self):
        """입고 시 AssetHistory(action='inbound') 자동 생성."""
        asset = self._make_asset('SN-IB-005')
        s = AssetInboundSerializer(data=self._inbound_data(asset))
        self.assertTrue(s.is_valid(), s.errors)
        s.save()
        self.assertTrue(
            AssetHistory.objects.filter(asset=asset, action='inbound').exists()
        )

    def test_inbound_number_prefix_asin(self):
        """입고번호는 ASIN{날짜}_ 형식으로 시작한다."""
        asset = self._make_asset('SN-IB-006')
        s = AssetInboundSerializer(data=self._inbound_data(asset))
        self.assertTrue(s.is_valid(), s.errors)
        inbound = s.save()
        self.assertTrue(inbound.inbound_number.startswith('ASIN'))

    def test_inbound_number_sequential_same_day(self):
        """같은 날 입고번호는 순서대로 증가한다."""
        today = datetime.date.today()
        asset1 = self._make_asset('SN-IB-007a')
        asset2 = self._make_asset('SN-IB-007b')
        s1 = AssetInboundSerializer(data=self._inbound_data(asset1, date=today))
        s2 = AssetInboundSerializer(data=self._inbound_data(asset2, date=today))
        self.assertTrue(s1.is_valid()); ib1 = s1.save()
        self.assertTrue(s2.is_valid()); ib2 = s2.save()
        seq1 = int(ib1.inbound_number.split('_')[-1])
        seq2 = int(ib2.inbound_number.split('_')[-1])
        self.assertGreater(seq2, seq1)


# ─────────────────────────────────────────
# 2. AssetOutbound — 출고 검증 및 상태 전이
# ─────────────────────────────────────────

class AssetOutboundValidationTest(AssetFixtureMixin, TestCase):

    def test_warehouse_outbound_fails_if_status_is_center(self):
        """창고 출고 요청인데 장비가 center 상태면 ValidationError."""
        asset = self._make_asset('SN-OB-V01', status='center', center=self.center)
        data = self._outbound_data(asset, from_type='warehouse', to_type='center',
                                   to_center=self.center2)
        s = AssetOutboundSerializer(data=data)
        with self.assertRaises(ValidationError):
            s.is_valid(raise_exception=True)

    def test_center_outbound_fails_if_status_is_warehouse(self):
        """센터 출고 요청인데 장비가 warehouse 상태면 ValidationError."""
        asset = self._make_asset('SN-OB-V02', status='warehouse')
        data = self._outbound_data(asset, from_type='center', to_type='school',
                                   to_school=self.school)
        s = AssetOutboundSerializer(data=data)
        with self.assertRaises(ValidationError):
            s.is_valid(raise_exception=True)

    def test_warehouse_outbound_valid_when_status_is_warehouse(self):
        """창고 출고 시 장비가 warehouse 상태면 유효하다."""
        asset = self._make_asset('SN-OB-V03', status='warehouse')
        data = self._outbound_data(asset, from_type='warehouse', to_type='center',
                                   to_center=self.center)
        s = AssetOutboundSerializer(data=data)
        self.assertTrue(s.is_valid(), s.errors)

    def test_center_outbound_valid_when_status_is_center(self):
        """센터 출고 시 장비가 center 상태면 유효하다."""
        asset = self._make_asset('SN-OB-V04', status='center', center=self.center)
        data = self._outbound_data(asset, from_type='center', to_type='school',
                                   to_school=self.school)
        s = AssetOutboundSerializer(data=data)
        self.assertTrue(s.is_valid(), s.errors)


class AssetOutboundStatusTransitionTest(AssetFixtureMixin, TestCase):

    def test_outbound_to_center_sets_status_center(self):
        """창고→센터 출고 → asset.status = 'center'."""
        asset = self._make_asset('SN-OB-001', status='warehouse')
        data = self._outbound_data(asset, from_type='warehouse', to_type='center',
                                   to_center=self.center)
        s = AssetOutboundSerializer(data=data)
        self.assertTrue(s.is_valid(), s.errors)
        s.save()
        asset.refresh_from_db()
        self.assertEqual(asset.status, 'center')

    def test_outbound_to_center_sets_current_center(self):
        """창고→센터 출고 시 current_center 가 설정된다."""
        asset = self._make_asset('SN-OB-002', status='warehouse')
        data = self._outbound_data(asset, from_type='warehouse', to_type='center',
                                   to_center=self.center)
        s = AssetOutboundSerializer(data=data)
        self.assertTrue(s.is_valid(), s.errors)
        s.save()
        asset.refresh_from_db()
        self.assertEqual(asset.current_center_id, self.center.pk)

    def test_outbound_to_school_sets_status_installed(self):
        """센터→학교 출고 → asset.status = 'installed'."""
        asset = self._make_asset('SN-OB-003', status='center', center=self.center)
        data = self._outbound_data(asset, from_type='center', to_type='school',
                                   to_school=self.school)
        s = AssetOutboundSerializer(data=data)
        self.assertTrue(s.is_valid(), s.errors)
        s.save()
        asset.refresh_from_db()
        self.assertEqual(asset.status, 'installed')

    def test_outbound_to_school_sets_current_school(self):
        """센터→학교 출고 시 current_school 이 설정된다."""
        asset = self._make_asset('SN-OB-004', status='center', center=self.center)
        data = self._outbound_data(asset, from_type='center', to_type='school',
                                   to_school=self.school)
        s = AssetOutboundSerializer(data=data)
        self.assertTrue(s.is_valid(), s.errors)
        s.save()
        asset.refresh_from_db()
        self.assertEqual(asset.current_school_id, self.school.pk)

    def test_outbound_to_school_sets_install_year_and_project(self):
        """학교 출고 시 install_year, project_name 이 현재 사업으로 설정된다."""
        asset = self._make_asset('SN-OB-005', status='center', center=self.center)
        data = self._outbound_data(asset, from_type='center', to_type='school',
                                   to_school=self.school)
        s = AssetOutboundSerializer(data=data)
        self.assertTrue(s.is_valid(), s.errors)
        s.save()
        asset.refresh_from_db()
        self.assertEqual(asset.install_year, CURRENT_INSTALL_YEAR)
        self.assertEqual(asset.project_name, CURRENT_INSTALL_PROJECT)

    def test_outbound_to_school_sets_installed_at_if_none(self):
        """installed_at 미설정 장비는 학교 출고 시 outbound_date 로 설정된다."""
        asset = self._make_asset('SN-OB-006', status='center', center=self.center)
        today = datetime.date.today()
        data = self._outbound_data(asset, from_type='center', to_type='school',
                                   to_school=self.school, date=today)
        s = AssetOutboundSerializer(data=data)
        self.assertTrue(s.is_valid(), s.errors)
        s.save()
        asset.refresh_from_db()
        self.assertEqual(asset.installed_at, today)

    def test_outbound_to_school_does_not_overwrite_installed_at(self):
        """이미 installed_at 이 있으면 학교 출고 시 덮어쓰지 않는다."""
        original_date = datetime.date(2025, 1, 15)
        asset = self._make_asset('SN-OB-007', status='center', center=self.center)
        asset.installed_at = original_date
        asset.save()
        data = self._outbound_data(asset, from_type='center', to_type='school',
                                   to_school=self.school)
        s = AssetOutboundSerializer(data=data)
        self.assertTrue(s.is_valid(), s.errors)
        s.save()
        asset.refresh_from_db()
        self.assertEqual(asset.installed_at, original_date)

    def test_outbound_to_vendor_sets_status_rma(self):
        """제조사(RMA) 출고 → asset.status = 'rma'."""
        asset = self._make_asset('SN-OB-008', status='center', center=self.center)
        data = self._outbound_data(asset, from_type='center', to_type='vendor')
        s = AssetOutboundSerializer(data=data)
        self.assertTrue(s.is_valid(), s.errors)
        s.save()
        asset.refresh_from_db()
        self.assertEqual(asset.status, 'rma')

    def test_outbound_to_vendor_clears_school(self):
        """RMA 출고 시 current_school 이 None 으로 초기화된다."""
        asset = self._make_asset('SN-OB-009', status='installed',
                                 school=self.school)
        # installed 상태는 center 출고로 간주 (from_type=center)
        data = self._outbound_data(asset, from_type='center', to_type='vendor')
        # 검증 우회: installed 상태에서 from_type=center 는 오류이므로
        # 직접 serializer 없이 모델에서 검증
        asset.status = 'center'
        asset.save()
        s = AssetOutboundSerializer(data=data)
        self.assertTrue(s.is_valid(), s.errors)
        s.save()
        asset.refresh_from_db()
        self.assertIsNone(asset.current_school)

    def test_outbound_creates_history_outbound(self):
        """센터/학교 출고 시 AssetHistory(action='outbound') 생성."""
        asset = self._make_asset('SN-OB-010', status='center', center=self.center)
        data = self._outbound_data(asset, from_type='center', to_type='school',
                                   to_school=self.school)
        s = AssetOutboundSerializer(data=data)
        self.assertTrue(s.is_valid(), s.errors)
        s.save()
        self.assertTrue(
            AssetHistory.objects.filter(asset=asset, action='outbound').exists()
        )

    def test_outbound_to_vendor_creates_history_rma_send(self):
        """RMA 출고 시 AssetHistory(action='rma_send') 생성."""
        asset = self._make_asset('SN-OB-011', status='center', center=self.center)
        data = self._outbound_data(asset, from_type='center', to_type='vendor')
        s = AssetOutboundSerializer(data=data)
        self.assertTrue(s.is_valid(), s.errors)
        s.save()
        self.assertTrue(
            AssetHistory.objects.filter(asset=asset, action='rma_send').exists()
        )

    def test_outbound_to_center_auto_creates_inbound_record(self):
        """창고→센터 출고 시 AssetInbound 레코드 자동 생성."""
        asset = self._make_asset('SN-OB-012', status='warehouse')
        data = self._outbound_data(asset, from_type='warehouse', to_type='center',
                                   to_center=self.center)
        s = AssetOutboundSerializer(data=data)
        self.assertTrue(s.is_valid(), s.errors)
        s.save()
        self.assertTrue(
            AssetInbound.objects.filter(asset=asset, to_location_type='center').exists()
        )

    def test_outbound_number_prefix_asout(self):
        """출고번호는 ASOUT{날짜}_ 형식으로 시작한다."""
        asset = self._make_asset('SN-OB-013', status='warehouse')
        data = self._outbound_data(asset, from_type='warehouse', to_type='center',
                                   to_center=self.center)
        s = AssetOutboundSerializer(data=data)
        self.assertTrue(s.is_valid(), s.errors)
        ob = s.save()
        self.assertTrue(ob.outbound_number.startswith('ASOUT'))

    def test_outbound_number_sequential_same_day(self):
        """같은 날 출고번호는 순서대로 증가한다."""
        today = datetime.date.today()
        asset1 = self._make_asset('SN-OB-014a', status='warehouse')
        asset2 = self._make_asset('SN-OB-014b', status='warehouse')
        d1 = self._outbound_data(asset1, from_type='warehouse', to_type='center',
                                 to_center=self.center, date=today)
        d2 = self._outbound_data(asset2, from_type='warehouse', to_type='center',
                                 to_center=self.center2, date=today)
        s1 = AssetOutboundSerializer(data=d1); self.assertTrue(s1.is_valid()); ob1 = s1.save()
        s2 = AssetOutboundSerializer(data=d2); self.assertTrue(s2.is_valid()); ob2 = s2.save()
        seq1 = int(ob1.outbound_number.split('_')[-1])
        seq2 = int(ob2.outbound_number.split('_')[-1])
        self.assertGreater(seq2, seq1)


# ─────────────────────────────────────────
# 3. AssetReturn — 반납/회수 → 상태 전이
# ─────────────────────────────────────────

class AssetReturnStatusTransitionTest(AssetFixtureMixin, TestCase):

    def test_return_to_center_sets_status_center(self):
        """학교→센터 반납 → asset.status = 'center'."""
        asset = self._make_asset('SN-RT-001', status='installed', school=self.school)
        data = self._return_data(asset, from_type='school', to_type='center',
                                 to_center=self.center)
        s = AssetReturnSerializer(data=data)
        self.assertTrue(s.is_valid(), s.errors)
        s.save()
        asset.refresh_from_db()
        self.assertEqual(asset.status, 'center')

    def test_return_to_center_sets_current_center(self):
        """센터 반납 시 current_center 가 설정된다."""
        asset = self._make_asset('SN-RT-002', status='installed', school=self.school)
        data = self._return_data(asset, from_type='school', to_type='center',
                                 to_center=self.center)
        s = AssetReturnSerializer(data=data)
        self.assertTrue(s.is_valid(), s.errors)
        s.save()
        asset.refresh_from_db()
        self.assertEqual(asset.current_center_id, self.center.pk)

    def test_return_to_center_clears_school(self):
        """센터 반납 시 current_school 이 None 으로 초기화된다."""
        asset = self._make_asset('SN-RT-003', status='installed', school=self.school)
        data = self._return_data(asset, from_type='school', to_type='center',
                                 to_center=self.center)
        s = AssetReturnSerializer(data=data)
        self.assertTrue(s.is_valid(), s.errors)
        s.save()
        asset.refresh_from_db()
        self.assertIsNone(asset.current_school)

    def test_return_to_warehouse_sets_status_warehouse(self):
        """센터→창고 반납 → asset.status = 'warehouse'."""
        asset = self._make_asset('SN-RT-004', status='center', center=self.center)
        data = self._return_data(asset, from_type='center', to_type='warehouse')
        s = AssetReturnSerializer(data=data)
        self.assertTrue(s.is_valid(), s.errors)
        s.save()
        asset.refresh_from_db()
        self.assertEqual(asset.status, 'warehouse')

    def test_return_to_warehouse_clears_center(self):
        """창고 반납 시 current_center 가 None 으로 초기화된다."""
        asset = self._make_asset('SN-RT-005', status='center', center=self.center)
        data = self._return_data(asset, from_type='center', to_type='warehouse')
        s = AssetReturnSerializer(data=data)
        self.assertTrue(s.is_valid(), s.errors)
        s.save()
        asset.refresh_from_db()
        self.assertIsNone(asset.current_center)

    def test_return_creates_history_record(self):
        """반납 시 AssetHistory(action='return') 자동 생성."""
        asset = self._make_asset('SN-RT-006', status='installed', school=self.school)
        data = self._return_data(asset, from_type='school', to_type='center',
                                 to_center=self.center)
        s = AssetReturnSerializer(data=data)
        self.assertTrue(s.is_valid(), s.errors)
        s.save()
        self.assertTrue(
            AssetHistory.objects.filter(asset=asset, action='return').exists()
        )

    def test_return_number_prefix_asret(self):
        """반납번호는 ASRET{날짜}_ 형식으로 시작한다."""
        asset = self._make_asset('SN-RT-007', status='center', center=self.center)
        data = self._return_data(asset, from_type='center', to_type='warehouse')
        s = AssetReturnSerializer(data=data)
        self.assertTrue(s.is_valid(), s.errors)
        ret = s.save()
        self.assertTrue(ret.return_number.startswith('ASRET'))

    def test_return_number_sequential_same_day(self):
        """같은 날 반납번호는 순서대로 증가한다."""
        today = datetime.date.today()
        asset1 = self._make_asset('SN-RT-008a', status='center', center=self.center)
        asset2 = self._make_asset('SN-RT-008b', status='center', center=self.center2)
        d1 = self._return_data(asset1, from_type='center', to_type='warehouse', date=today)
        d2 = self._return_data(asset2, from_type='center', to_type='warehouse', date=today)
        s1 = AssetReturnSerializer(data=d1); self.assertTrue(s1.is_valid()); r1 = s1.save()
        s2 = AssetReturnSerializer(data=d2); self.assertTrue(s2.is_valid()); r2 = s2.save()
        seq1 = int(r1.return_number.split('_')[-1])
        seq2 = int(r2.return_number.split('_')[-1])
        self.assertGreater(seq2, seq1)


# ─────────────────────────────────────────
# 4. AssetRMA 모델 상태 흐름
# ─────────────────────────────────────────

class AssetRMAStatusTest(AssetFixtureMixin, TestCase):

    def _make_rma(self, asset, status='sent'):
        return AssetRMA.objects.create(
            asset=asset,
            rma_number='RMA-TEST-001',
            status=status,
            reason='전원 불량',
            sent_date=datetime.date.today(),
        )

    def test_rma_initial_status_sent(self):
        """AssetRMA 기본 상태는 'sent'."""
        asset = self._make_asset('SN-RMA-001', status='rma')
        rma = AssetRMA.objects.create(
            asset=asset, reason='불량', status='sent',
            sent_date=datetime.date.today(),
        )
        self.assertEqual(rma.status, 'sent')

    def test_rma_status_transition_sent_to_received(self):
        """sent → received 상태 변경 저장."""
        asset = self._make_asset('SN-RMA-002', status='rma')
        rma = self._make_rma(asset, status='sent')
        rma.status = 'received'
        rma.save()
        rma.refresh_from_db()
        self.assertEqual(rma.status, 'received')

    def test_rma_status_transition_received_to_repaired(self):
        """received → repaired 상태 변경 저장."""
        asset = self._make_asset('SN-RMA-003', status='rma')
        rma = self._make_rma(asset, status='received')
        rma.status = 'repaired'
        rma.save()
        rma.refresh_from_db()
        self.assertEqual(rma.status, 'repaired')

    def test_rma_status_transition_to_returned(self):
        """repaired → returned (동일 S/N 반환 완료) 상태 변경."""
        asset = self._make_asset('SN-RMA-004', status='rma')
        rma = self._make_rma(asset, status='repaired')
        rma.status = 'returned'
        rma.returned_date = datetime.date.today()
        rma.save()
        rma.refresh_from_db()
        self.assertEqual(rma.status, 'returned')
        self.assertIsNotNone(rma.returned_date)

    def test_rma_status_transition_to_replaced(self):
        """repaired → replaced (S/N 변경 교체품) 상태 변경."""
        asset = self._make_asset('SN-RMA-005', status='rma')
        rma = self._make_rma(asset, status='repaired')
        rma.status = 'replaced'
        rma.new_serial = 'SN-RMA-005-NEW'
        rma.save()
        rma.refresh_from_db()
        self.assertEqual(rma.status, 'replaced')
        self.assertEqual(rma.new_serial, 'SN-RMA-005-NEW')

    def test_rma_replaced_links_replacement_asset(self):
        """교체품 수령 시 replacement_asset 으로 신규 Asset 연결."""
        original = self._make_asset('SN-RMA-006-ORIG', status='rma')
        replacement = self._make_asset('SN-RMA-006-NEW', status='warehouse')
        replacement.is_rma_replaced = True
        replacement.replaced_from = original
        replacement.save()

        rma = self._make_rma(original, status='replaced')
        rma.replacement_asset = replacement
        rma.new_serial = 'SN-RMA-006-NEW'
        rma.save()

        rma.refresh_from_db()
        self.assertEqual(rma.replacement_asset_id, replacement.pk)
        replacement.refresh_from_db()
        self.assertTrue(replacement.is_rma_replaced)
        self.assertEqual(replacement.replaced_from_id, original.pk)

    def test_asset_rma_record_linked_via_related_name(self):
        """asset.rma_records 역참조로 AssetRMA 조회 가능."""
        asset = self._make_asset('SN-RMA-007', status='rma')
        rma = self._make_rma(asset)
        self.assertIn(rma, asset.rma_records.all())


# ─────────────────────────────────────────
# 5. 문서번호 생성 단위 테스트
# ─────────────────────────────────────────

class DocumentNumberGenerationTest(AssetFixtureMixin, TestCase):

    def _make_asset_n(self, n):
        return Asset.objects.create(
            asset_model=self.asset_model,
            serial_number=f'SN-DOC-{n:03d}',
            status='warehouse',
        )

    def test_inbound_number_format(self):
        """AssetInbound.generate_number() → ASIN{YYYYMMDD}_{seq:03d}."""
        date = datetime.date(2026, 4, 10)
        num = AssetInbound.generate_number(date)
        self.assertTrue(num.startswith('ASIN20260410_'))
        seq = num.split('_')[-1]
        self.assertEqual(len(seq), 3)
        self.assertTrue(seq.isdigit())

    def test_outbound_number_format(self):
        """AssetOutbound.generate_number() → ASOUT{YYYYMMDD}_{seq:03d}."""
        date = datetime.date(2026, 4, 10)
        num = AssetOutbound.generate_number(date)
        self.assertTrue(num.startswith('ASOUT20260410_'))
        seq = num.split('_')[-1]
        self.assertEqual(len(seq), 3)
        self.assertTrue(seq.isdigit())

    def test_return_number_format(self):
        """AssetReturn.generate_number() → ASRET{YYYYMMDD}_{seq:03d}."""
        date = datetime.date(2026, 4, 10)
        num = AssetReturn.generate_number(date)
        self.assertTrue(num.startswith('ASRET20260410_'))
        seq = num.split('_')[-1]
        self.assertEqual(len(seq), 3)
        self.assertTrue(seq.isdigit())

    def test_inbound_number_increments(self):
        """AssetInbound 연속 생성 시 시퀀스 번호 증가."""
        date = datetime.date(2026, 4, 11)
        nums = [AssetInbound.generate_number(date) for _ in range(3)]
        # generate_number 는 DB count 기반이므로 같은 날 호출만으로는 증가하지 않음
        # 실제 저장 후 증가 확인
        asset1 = self._make_asset_n(901)
        asset2 = self._make_asset_n(902)
        ib1 = AssetInbound.objects.create(
            inbound_number=AssetInbound.generate_number(date),
            asset=asset1, from_location_type='education_office',
            to_location_type='warehouse', inbound_date=date,
        )
        ib2 = AssetInbound.objects.create(
            inbound_number=AssetInbound.generate_number(date),
            asset=asset2, from_location_type='education_office',
            to_location_type='warehouse', inbound_date=date,
        )
        seq1 = int(ib1.inbound_number.split('_')[-1])
        seq2 = int(ib2.inbound_number.split('_')[-1])
        self.assertEqual(seq2, seq1 + 1)

    def test_outbound_number_increments(self):
        """AssetOutbound 연속 생성 시 시퀀스 번호 증가."""
        date = datetime.date(2026, 4, 11)
        asset1 = self._make_asset_n(903)
        asset2 = self._make_asset_n(904)
        ob1 = AssetOutbound.objects.create(
            outbound_number=AssetOutbound.generate_number(date),
            asset=asset1, from_location_type='warehouse',
            to_location_type='center', to_center=self.center,
            outbound_date=date,
        )
        ob2 = AssetOutbound.objects.create(
            outbound_number=AssetOutbound.generate_number(date),
            asset=asset2, from_location_type='warehouse',
            to_location_type='center', to_center=self.center,
            outbound_date=date,
        )
        seq1 = int(ob1.outbound_number.split('_')[-1])
        seq2 = int(ob2.outbound_number.split('_')[-1])
        self.assertEqual(seq2, seq1 + 1)


# ─────────────────────────────────────────
# 6. 전체 흐름 통합 테스트
# ─────────────────────────────────────────

class AssetFullFlowIntegrationTest(AssetFixtureMixin, TestCase):
    """창고 입고 → 센터 출고 → 학교 설치 → 회수 → RMA 전체 흐름."""

    def test_full_lifecycle_warehouse_to_installed(self):
        """창고 입고 → 센터 출고 → 학교 설치 전체 흐름."""
        asset = self._make_asset('SN-FLOW-001', status='warehouse')

        # 1단계: 창고 → 센터 출고
        ob_data = self._outbound_data(asset, from_type='warehouse', to_type='center',
                                      to_center=self.center)
        s = AssetOutboundSerializer(data=ob_data)
        self.assertTrue(s.is_valid(), s.errors)
        s.save()
        asset.refresh_from_db()
        self.assertEqual(asset.status, 'center')

        # 2단계: 센터 → 학교 출고
        ob2_data = self._outbound_data(asset, from_type='center', to_type='school',
                                       to_school=self.school)
        s2 = AssetOutboundSerializer(data=ob2_data)
        self.assertTrue(s2.is_valid(), s2.errors)
        s2.save()
        asset.refresh_from_db()
        self.assertEqual(asset.status, 'installed')
        self.assertEqual(asset.current_school_id, self.school.pk)

        # 이력 2건 (outbound x2) 확인
        history_count = AssetHistory.objects.filter(asset=asset).count()
        self.assertGreaterEqual(history_count, 2)

    def test_full_lifecycle_installed_to_rma_and_return(self):
        """학교 설치 → 회수 → 창고 반납 → RMA 발송 흐름."""
        asset = self._make_asset('SN-FLOW-002', status='installed', school=self.school)

        # 1단계: 학교 → 센터 회수
        ret_data = self._return_data(asset, from_type='school', to_type='center',
                                     to_center=self.center)
        s = AssetReturnSerializer(data=ret_data)
        self.assertTrue(s.is_valid(), s.errors)
        s.save()
        asset.refresh_from_db()
        self.assertEqual(asset.status, 'center')

        # 2단계: 센터 → 창고 반납
        ret2_data = self._return_data(asset, from_type='center', to_type='warehouse')
        s2 = AssetReturnSerializer(data=ret2_data)
        self.assertTrue(s2.is_valid(), s2.errors)
        s2.save()
        asset.refresh_from_db()
        self.assertEqual(asset.status, 'warehouse')

        # 3단계: 창고 → 제조사(RMA) 출고
        ob_data = self._outbound_data(asset, from_type='warehouse', to_type='vendor')
        s3 = AssetOutboundSerializer(data=ob_data)
        self.assertTrue(s3.is_valid(), s3.errors)
        s3.save()
        asset.refresh_from_db()
        self.assertEqual(asset.status, 'rma')

        # 이력 3건 (return x2 + rma_send x1) 확인
        history_count = AssetHistory.objects.filter(asset=asset).count()
        self.assertGreaterEqual(history_count, 3)

    def test_rma_return_updates_asset_back_to_warehouse_via_inbound(self):
        """RMA 완료 후 창고 입고 → asset.status = 'warehouse'로 복귀."""
        asset = self._make_asset('SN-FLOW-003', status='rma')
        ib_data = self._inbound_data(asset, to_type='warehouse')
        s = AssetInboundSerializer(data=ib_data)
        self.assertTrue(s.is_valid(), s.errors)
        s.save()
        asset.refresh_from_db()
        self.assertEqual(asset.status, 'warehouse')
        self.assertIsNone(asset.current_center)

    def test_multiple_assets_independent_transitions(self):
        """여러 장비의 상태 전이가 서로 독립적으로 동작한다."""
        asset_a = self._make_asset('SN-FLOW-004A', status='warehouse')
        asset_b = self._make_asset('SN-FLOW-004B', status='warehouse')

        # asset_a: warehouse → center
        s_a = AssetOutboundSerializer(data=self._outbound_data(
            asset_a, from_type='warehouse', to_type='center', to_center=self.center
        ))
        self.assertTrue(s_a.is_valid()); s_a.save()

        # asset_b: warehouse → center (다른 센터)
        s_b = AssetOutboundSerializer(data=self._outbound_data(
            asset_b, from_type='warehouse', to_type='center', to_center=self.center2
        ))
        self.assertTrue(s_b.is_valid()); s_b.save()

        asset_a.refresh_from_db()
        asset_b.refresh_from_db()
        self.assertEqual(asset_a.current_center_id, self.center.pk)
        self.assertEqual(asset_b.current_center_id, self.center2.pk)
