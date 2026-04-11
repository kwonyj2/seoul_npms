"""
자재 재고 증감 테스트 — Phase 3-2

검증 흐름: 창고(Warehouse) → 지원청(Center) → 기사(Worker) → 학교 현장
"""
import datetime
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.materials.models import (
    Material, MaterialCategory, WarehouseInventory, CenterInventory,
    WorkerInventory, MaterialInbound, MaterialOutbound, MaterialReturn,
    MaterialTransfer, MaterialUsage,
)
from apps.schools.models import SupportCenter, School

User = get_user_model()


# ─────────────────────────────────────────
# 공통 Fixture
# ─────────────────────────────────────────

class MaterialTestBase(TestCase):
    """공통 픽스처: 자재·창고·지원청·유저"""

    @classmethod
    def setUpTestData(cls):
        cls.center = SupportCenter.objects.create(name='동부교육지원청', code='EAST')
        cls.center2 = SupportCenter.objects.create(name='서부교육지원청', code='WEST')

        cls.admin = User.objects.create_user(
            username='inv_admin', email='ia@test.com',
            password='pass', name='관리자', role='admin',
            support_center=cls.center,
        )
        cls.worker = User.objects.create_user(
            username='inv_worker', email='iw@test.com',
            password='pass', name='기사1', role='worker',
            support_center=cls.center,
        )

        cls.cat = MaterialCategory.objects.create(
            code='CAT01', name='케이블', type_code='cable'
        )
        cls.mat = Material.objects.create(
            category=cls.cat, code='M001',
            name='UTP 케이블 Cat6', unit='m', unit_price=500, min_stock=50
        )
        cls.mat2 = Material.objects.create(
            category=cls.cat, code='M002',
            name='광케이블 SM', unit='m', unit_price=1200, min_stock=20
        )

    def _make_warehouse(self, qty):
        """창고 재고 설정 헬퍼"""
        inv, _ = WarehouseInventory.objects.get_or_create(
            material=self.mat, defaults={'quantity': qty}
        )
        inv.quantity = qty
        inv.save()
        return inv

    def _make_center_inv(self, center, qty):
        """지원청 재고 설정 헬퍼"""
        cinv, _ = CenterInventory.objects.get_or_create(
            support_center=center, material=self.mat, defaults={'quantity': qty}
        )
        cinv.quantity = qty
        cinv.save()
        return cinv

    def _today(self):
        return timezone.localdate()


# ─────────────────────────────────────────
# 1. WarehouseInventory 모델 직접 테스트
# ─────────────────────────────────────────

class WarehouseInventoryModelTest(MaterialTestBase):

    def test_initial_quantity_zero(self):
        """새 창고 재고는 0"""
        inv = WarehouseInventory.objects.create(material=self.mat2, quantity=0)
        self.assertEqual(inv.quantity, 0)

    def test_quantity_increases_on_add(self):
        """수량 직접 증가"""
        inv = self._make_warehouse(100)
        inv.quantity += 50
        inv.save()
        inv.refresh_from_db()
        self.assertEqual(inv.quantity, 150)

    def test_quantity_decreases_on_subtract(self):
        """수량 직접 감소"""
        inv = self._make_warehouse(100)
        inv.quantity -= 30
        inv.save()
        inv.refresh_from_db()
        self.assertEqual(inv.quantity, 70)

    def test_one_to_one_material_constraint(self):
        """Material 당 창고 재고 1개 (unique)"""
        from django.db import IntegrityError
        self._make_warehouse(10)
        with self.assertRaises(IntegrityError):
            WarehouseInventory.objects.create(material=self.mat, quantity=20)

    def test_is_low_when_at_min_stock(self):
        """min_stock 이하 → is_low True"""
        inv = self._make_warehouse(50)   # min_stock=50
        is_low = self.mat.min_stock > 0 and inv.quantity <= self.mat.min_stock
        self.assertTrue(is_low)

    def test_not_low_above_min_stock(self):
        """min_stock 초과 → is_low False"""
        inv = self._make_warehouse(51)
        is_low = self.mat.min_stock > 0 and inv.quantity <= self.mat.min_stock
        self.assertFalse(is_low)


# ─────────────────────────────────────────
# 2. MaterialInbound Serializer — 입고 → 창고 증가
# ─────────────────────────────────────────

class InboundSerializerTest(MaterialTestBase):

    def _create_inbound(self, qty, inbound_type='normal', from_center=None):
        from apps.materials.serializers import MaterialInboundSerializer
        data = {
            'material': self.mat.id,
            'quantity': qty,
            'unit_price': 500,
            'inbound_type': inbound_type,
            'inbound_date': str(self._today()),
        }
        if from_center:
            data['from_center'] = from_center.id
        ser = MaterialInboundSerializer(data=data)
        ser.is_valid(raise_exception=True)
        return ser.save(received_by=self.admin)

    def test_inbound_increases_warehouse_qty(self):
        """일반 입고 → 창고 재고 증가"""
        self._make_warehouse(100)
        self._create_inbound(50)
        inv = WarehouseInventory.objects.get(material=self.mat)
        self.assertEqual(inv.quantity, 150)

    def test_inbound_creates_warehouse_if_not_exists(self):
        """창고 재고 없을 때 입고 → 자동 생성"""
        WarehouseInventory.objects.filter(material=self.mat).delete()
        self._create_inbound(80)
        inv = WarehouseInventory.objects.get(material=self.mat)
        self.assertEqual(inv.quantity, 80)

    def test_inbound_number_auto_generated(self):
        """입고번호 자동 생성 (IN + 날짜 형식)"""
        inbound = self._create_inbound(10)
        self.assertTrue(inbound.inbound_number.startswith('IN'))

    def test_multiple_inbounds_accumulate(self):
        """여러 번 입고 → 누적 증가"""
        self._make_warehouse(0)
        self._create_inbound(30)
        self._create_inbound(20)
        inv = WarehouseInventory.objects.get(material=self.mat)
        self.assertEqual(inv.quantity, 50)

    def test_return_inbound_increases_warehouse(self):
        """반납 입고 → 창고 재고 증가"""
        self._make_warehouse(100)
        self._make_center_inv(self.center, 30)
        self._create_inbound(20, inbound_type='return', from_center=self.center)
        inv = WarehouseInventory.objects.get(material=self.mat)
        self.assertEqual(inv.quantity, 120)

    def test_return_inbound_decreases_center_stock(self):
        """반납 입고 → 해당 센터 재고 감소"""
        self._make_warehouse(100)
        self._make_center_inv(self.center, 30)
        self._create_inbound(20, inbound_type='return', from_center=self.center)
        cinv = CenterInventory.objects.get(material=self.mat, support_center=self.center)
        self.assertEqual(cinv.quantity, 10)

    def test_return_inbound_creates_outbound_record(self):
        """반납 입고 시 출고 이력 자동 생성"""
        self._make_warehouse(50)
        self._make_center_inv(self.center, 20)
        before_count = MaterialOutbound.objects.count()
        self._create_inbound(15, inbound_type='return', from_center=self.center)
        self.assertEqual(MaterialOutbound.objects.count(), before_count + 1)

    def test_inbound_update_adjusts_warehouse(self):
        """입고 수량 수정 → 창고 재고 차이 반영"""
        self._make_warehouse(100)
        inbound = self._create_inbound(30)
        # 창고: 100 + 30 = 130
        # 수량을 30 → 50 으로 수정 (diff = +20)
        from apps.materials.serializers import MaterialInboundSerializer
        ser = MaterialInboundSerializer(
            inbound, data={'quantity': 50}, partial=True
        )
        ser.is_valid(raise_exception=True)
        ser.save()
        inv = WarehouseInventory.objects.get(material=self.mat)
        self.assertEqual(inv.quantity, 150)   # 130 + 20 = 150


# ─────────────────────────────────────────
# 3. MaterialOutbound Serializer — 출고 → 창고 감소 + 센터 증가
# ─────────────────────────────────────────

class OutboundSerializerTest(MaterialTestBase):

    def _create_outbound(self, qty, to_center=None):
        from apps.materials.serializers import MaterialOutboundSerializer
        self._make_warehouse(200)
        data = {
            'material': self.mat.id,
            'quantity': qty,
            'from_warehouse': True,
            'outbound_date': str(self._today()),
        }
        if to_center:
            data['to_center'] = to_center.id
        ser = MaterialOutboundSerializer(data=data)
        ser.is_valid(raise_exception=True)
        return ser.save(issued_by=self.admin)

    def test_outbound_decreases_warehouse_qty(self):
        """출고 → 창고 재고 감소"""
        self._create_outbound(60)
        inv = WarehouseInventory.objects.get(material=self.mat)
        self.assertEqual(inv.quantity, 140)

    def test_outbound_to_center_increases_center_qty(self):
        """출고(지원청 대상) → 해당 센터 재고 증가"""
        self._create_outbound(40, to_center=self.center)
        cinv = CenterInventory.objects.get(material=self.mat, support_center=self.center)
        self.assertEqual(cinv.quantity, 40)

    def test_outbound_creates_center_inventory_if_not_exists(self):
        """지원청 재고 없을 때 출고 → 자동 생성"""
        CenterInventory.objects.filter(material=self.mat, support_center=self.center).delete()
        self._create_outbound(25, to_center=self.center)
        cinv = CenterInventory.objects.get(material=self.mat, support_center=self.center)
        self.assertEqual(cinv.quantity, 25)

    def test_outbound_insufficient_stock_raises(self):
        """재고 부족 출고 → ValidationError"""
        from rest_framework.exceptions import ValidationError
        from apps.materials.serializers import MaterialOutboundSerializer
        self._make_warehouse(10)
        ser = MaterialOutboundSerializer(data={
            'material': self.mat.id,
            'quantity': 100,   # 재고(10) 초과
            'from_warehouse': True,
            'outbound_date': str(self._today()),
        })
        with self.assertRaises(ValidationError):
            ser.is_valid(raise_exception=True)

    def test_outbound_no_warehouse_raises(self):
        """창고 재고 없을 때 출고 → ValidationError"""
        from rest_framework.exceptions import ValidationError
        from apps.materials.serializers import MaterialOutboundSerializer
        WarehouseInventory.objects.filter(material=self.mat).delete()
        ser = MaterialOutboundSerializer(data={
            'material': self.mat.id,
            'quantity': 10,
            'from_warehouse': True,
            'outbound_date': str(self._today()),
        })
        with self.assertRaises(ValidationError):
            ser.is_valid(raise_exception=True)

    def test_outbound_number_auto_generated(self):
        """출고번호 자동 생성 (OUT + 날짜 형식)"""
        outbound = self._create_outbound(10)
        self.assertTrue(outbound.outbound_number.startswith('OUT'))

    def test_multiple_outbounds_accumulate(self):
        """여러 번 출고 → 창고 재고 누적 감소"""
        # _create_outbound 는 내부에서 창고를 200 으로 재설정하므로
        # 여러 번 출고 테스트는 Serializer 를 직접 호출
        from apps.materials.serializers import MaterialOutboundSerializer
        self._make_warehouse(100)
        for qty in (20, 30):
            ser = MaterialOutboundSerializer(data={
                'material': self.mat.id, 'quantity': qty,
                'from_warehouse': True,
                'outbound_date': str(self._today()),
            })
            ser.is_valid(raise_exception=True)
            ser.save(issued_by=self.admin)
        inv = WarehouseInventory.objects.get(material=self.mat)
        self.assertEqual(inv.quantity, 50)   # 100 - 20 - 30


# ─────────────────────────────────────────
# 4. MaterialReturn — 반납 → 센터 재고 증가
# ─────────────────────────────────────────

class MaterialReturnSerializerTest(MaterialTestBase):

    def _create_return(self, qty, initial_center_qty=10):
        from apps.materials.serializers import MaterialReturnSerializer
        self._make_center_inv(self.center, initial_center_qty)
        data = {
            'material': self.mat.id,
            'quantity': qty,
            'to_center': self.center.id,
            'return_date': str(self._today()),
        }
        ser = MaterialReturnSerializer(data=data)
        ser.is_valid(raise_exception=True)
        return ser.save(received_by=self.admin)

    def test_return_increases_center_qty(self):
        """반납 → 센터 재고 증가"""
        self._create_return(15)
        cinv = CenterInventory.objects.get(material=self.mat, support_center=self.center)
        self.assertEqual(cinv.quantity, 25)   # 10 + 15

    def test_return_number_auto_generated(self):
        """반납번호 자동 생성 (RET + 날짜)"""
        ret = self._create_return(5)
        self.assertTrue(ret.return_number.startswith('RET'))

    def test_return_creates_center_inv_if_not_exists(self):
        """센터 재고 없을 때 반납 → 자동 생성 (기존 재고 없이 시작)"""
        from apps.materials.serializers import MaterialReturnSerializer
        # 센터 재고 완전히 제거 후 직접 반납 생성
        CenterInventory.objects.filter(
            material=self.mat, support_center=self.center
        ).delete()
        data = {
            'material': self.mat.id, 'quantity': 20,
            'to_center': self.center.id,
            'return_date': str(self._today()),
        }
        ser = MaterialReturnSerializer(data=data)
        ser.is_valid(raise_exception=True)
        ser.save(received_by=self.admin)
        cinv = CenterInventory.objects.get(
            material=self.mat, support_center=self.center
        )
        self.assertEqual(cinv.quantity, 20)


# ─────────────────────────────────────────
# 5. 문서번호 생성 (generate_number)
# ─────────────────────────────────────────

class DocumentNumberGenerationTest(MaterialTestBase):

    def test_inbound_number_format(self):
        """입고번호: IN + YYYYMMDD + _NNN"""
        num = MaterialInbound.generate_number(self._today())
        import re
        self.assertRegex(num, r'^IN\d{8}_\d{3}$')

    def test_outbound_number_format(self):
        """출고번호: OUT + YYYYMMDD + _NNN"""
        num = MaterialOutbound.generate_number(self._today())
        self.assertRegex(num, r'^OUT\d{8}_\d{3}$')

    def test_return_number_format(self):
        """반납번호: RET + YYYYMMDD + _NNN"""
        num = MaterialReturn.generate_number(self._today())
        self.assertRegex(num, r'^RET\d{8}_\d{3}$')

    def test_inbound_number_sequential(self):
        """같은 날 입고번호 순번 증가"""
        from apps.materials.serializers import MaterialInboundSerializer
        self._make_warehouse(200)

        def make_inbound(qty):
            ser = MaterialInboundSerializer(data={
                'material': self.mat.id, 'quantity': qty,
                'inbound_date': str(self._today()),
            })
            ser.is_valid(raise_exception=True)
            return ser.save(received_by=self.admin)

        n1 = make_inbound(10)
        n2 = make_inbound(10)
        seq1 = int(n1.inbound_number.split('_')[-1])
        seq2 = int(n2.inbound_number.split('_')[-1])
        self.assertEqual(seq2, seq1 + 1)


# ─────────────────────────────────────────
# 6. 전체 흐름 통합 테스트
# ─────────────────────────────────────────

class InventoryFlowIntegrationTest(MaterialTestBase):
    """창고 입고 → 지원청 출고 → 반납 전 과정 재고 일관성"""

    def test_full_flow_warehouse_to_center_to_return(self):
        """
        창고 입고 200 → 지원청 출고 80 → 반납 30
        창고: 200 → 120 (출고) → 변동없음
        센터: 0  → 80 (출고) → 110 (반납)
        """
        from apps.materials.serializers import (
            MaterialInboundSerializer, MaterialOutboundSerializer,
            MaterialReturnSerializer,
        )
        WarehouseInventory.objects.filter(material=self.mat).delete()
        CenterInventory.objects.filter(material=self.mat).delete()

        # 입고 200
        ser = MaterialInboundSerializer(data={
            'material': self.mat.id, 'quantity': 200,
            'inbound_date': str(self._today()),
        })
        ser.is_valid(raise_exception=True)
        ser.save(received_by=self.admin)

        wh = WarehouseInventory.objects.get(material=self.mat)
        self.assertEqual(wh.quantity, 200)

        # 지원청 출고 80
        ser2 = MaterialOutboundSerializer(data={
            'material': self.mat.id, 'quantity': 80,
            'from_warehouse': True,
            'to_center': self.center.id,
            'outbound_date': str(self._today()),
        })
        ser2.is_valid(raise_exception=True)
        ser2.save(issued_by=self.admin)

        wh.refresh_from_db()
        self.assertEqual(wh.quantity, 120)
        cinv = CenterInventory.objects.get(material=self.mat, support_center=self.center)
        self.assertEqual(cinv.quantity, 80)

        # 반납 30
        ser3 = MaterialReturnSerializer(data={
            'material': self.mat.id, 'quantity': 30,
            'to_center': self.center.id,
            'return_date': str(self._today()),
        })
        ser3.is_valid(raise_exception=True)
        ser3.save(received_by=self.admin)

        cinv.refresh_from_db()
        self.assertEqual(cinv.quantity, 110)
        wh.refresh_from_db()
        self.assertEqual(wh.quantity, 120)   # 반납은 창고 재고 무변동

    def test_outbound_then_update_adjusts_inventory(self):
        """출고 후 수량 수정 → 재고 차이 반영"""
        from apps.materials.serializers import MaterialOutboundSerializer
        self._make_warehouse(100)

        ser = MaterialOutboundSerializer(data={
            'material': self.mat.id, 'quantity': 30,
            'from_warehouse': True, 'to_center': self.center.id,
            'outbound_date': str(self._today()),
        })
        ser.is_valid(raise_exception=True)
        outbound = ser.save(issued_by=self.admin)

        wh = WarehouseInventory.objects.get(material=self.mat)
        self.assertEqual(wh.quantity, 70)

        # 30 → 50 으로 수정 (추가 20 필요)
        ser2 = MaterialOutboundSerializer(
            outbound,
            data={'quantity': 50},
            partial=True,
        )
        ser2.is_valid(raise_exception=True)
        ser2.save()

        wh.refresh_from_db()
        self.assertEqual(wh.quantity, 50)   # 70 - 20 = 50
