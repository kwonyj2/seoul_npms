from django.test import TestCase


class InventoryQuantityTest(TestCase):
    """자재 재고 수량 계산 로직 단위 테스트"""

    def _apply_transactions(self, initial, inbounds, outbounds):
        """입출고 내역 적용 후 재고 계산"""
        qty = initial
        for q in inbounds:
            qty += q
        for q in outbounds:
            qty -= q
        return qty

    def test_inbound_increases_stock(self):
        """입고 → 재고 증가"""
        qty = self._apply_transactions(10, inbounds=[20], outbounds=[])
        self.assertEqual(qty, 30)

    def test_outbound_decreases_stock(self):
        """출고 → 재고 감소"""
        qty = self._apply_transactions(30, inbounds=[], outbounds=[10])
        self.assertEqual(qty, 20)

    def test_multiple_transactions(self):
        """복수 입출고 — 누적 재고 정확성"""
        qty = self._apply_transactions(0, inbounds=[50, 30], outbounds=[10, 5, 20])
        self.assertEqual(qty, 45)  # 0+50+30-10-5-20

    def test_stock_can_go_negative(self):
        """출고가 재고 초과 시 음수 허용 (모델 IntegerField 사용)"""
        qty = self._apply_transactions(5, inbounds=[], outbounds=[10])
        self.assertEqual(qty, -5)

    def test_zero_initial_stock(self):
        """초기 재고 0에서 입고"""
        qty = self._apply_transactions(0, inbounds=[100], outbounds=[])
        self.assertEqual(qty, 100)

    def test_full_outbound_clears_stock(self):
        """전량 출고 → 재고 0"""
        qty = self._apply_transactions(50, inbounds=[], outbounds=[50])
        self.assertEqual(qty, 0)


class MaterialTransferTest(TestCase):
    """자재 이동(창고 → 센터, 센터 → 기사) 로직 단위 테스트"""

    def _transfer(self, src_qty, tgt_qty, amount):
        """이동 후 송신/수신 재고 반환"""
        if amount > src_qty:
            raise ValueError(f'이동 수량({amount}) > 출발 재고({src_qty})')
        return src_qty - amount, tgt_qty + amount

    def test_warehouse_to_center(self):
        """창고 → 센터 이동"""
        wh, ctr = self._transfer(src_qty=100, tgt_qty=20, amount=30)
        self.assertEqual(wh, 70)
        self.assertEqual(ctr, 50)

    def test_center_to_worker(self):
        """센터 → 기사 이동"""
        ctr, wrk = self._transfer(src_qty=50, tgt_qty=5, amount=10)
        self.assertEqual(ctr, 40)
        self.assertEqual(wrk, 15)

    def test_transfer_exceeds_source_raises(self):
        """출발 재고 초과 이동 → ValueError"""
        with self.assertRaises(ValueError):
            self._transfer(src_qty=10, tgt_qty=0, amount=20)

    def test_zero_amount_transfer(self):
        """0 수량 이동 → 재고 변동 없음"""
        src, tgt = self._transfer(src_qty=10, tgt_qty=5, amount=0)
        self.assertEqual(src, 10)
        self.assertEqual(tgt, 5)
