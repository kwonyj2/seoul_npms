"""
materials 앱 모델
자재 관리 (중앙창고 → 지원청 → 학교 흐름)
"""
from django.db import models
from django.utils import timezone


class MaterialCategory(models.Model):
    """자재 분류"""
    CATEGORY_CHOICES = [
        ('cable',    '케이블'),
        ('connector','커넥터/잭'),
        ('tool',     '공구'),
        ('equipment','장비'),
        ('other',    '기타'),
    ]
    code      = models.CharField('코드', max_length=20, unique=True)
    name      = models.CharField('분류명', max_length=50)
    type_code = models.CharField('유형', max_length=20, choices=CATEGORY_CHOICES, default='other')
    order     = models.PositiveSmallIntegerField('정렬순서', default=0)
    is_active = models.BooleanField('활성', default=True)

    class Meta:
        db_table = 'material_categories'
        verbose_name = '자재 분류'
        verbose_name_plural = '자재 분류 목록'
        ordering = ['order']

    def __str__(self):
        return self.name


class Material(models.Model):
    """자재 마스터"""
    UNIT_CHOICES = [
        ('ea',  '개(EA)'),
        ('m',   '미터(m)'),
        ('roll','롤(Roll)'),
        ('set', '세트(Set)'),
        ('box', '박스(Box)'),
    ]
    category     = models.ForeignKey(MaterialCategory, on_delete=models.PROTECT, verbose_name='분류')
    code         = models.CharField('자재코드', max_length=30, unique=True)
    name         = models.CharField('자재명', max_length=100)
    spec         = models.CharField('규격/사양', max_length=200, blank=True)
    unit         = models.CharField('단위', max_length=10, choices=UNIT_CHOICES, default='ea')
    unit_price   = models.DecimalField('단가', max_digits=10, decimal_places=0, default=0)
    min_stock    = models.PositiveIntegerField('최소재고', default=0)
    supplier     = models.CharField('공급업체', max_length=100, blank=True)
    is_active    = models.BooleanField('활성', default=True)
    note         = models.TextField('비고', blank=True)
    created_at   = models.DateTimeField('등록일시', auto_now_add=True)

    class Meta:
        db_table = 'materials'
        verbose_name = '자재'
        verbose_name_plural = '자재 목록'
        ordering = ['category', 'name']

    def __str__(self):
        return f'[{self.code}] {self.name}'


class WarehouseInventory(models.Model):
    """중앙 창고 재고"""
    material   = models.OneToOneField(Material, on_delete=models.PROTECT, verbose_name='자재', related_name='warehouse_inventory')
    quantity   = models.IntegerField('재고수량', default=0)
    updated_at = models.DateTimeField('갱신일시', auto_now=True)

    class Meta:
        db_table = 'warehouse_inventory'
        verbose_name = '창고 재고'

    def __str__(self):
        return f'{self.material.name}: {self.quantity}'


class CenterInventory(models.Model):
    """지원청 센터 재고"""
    support_center = models.ForeignKey('schools.SupportCenter', on_delete=models.CASCADE, verbose_name='지원청')
    material       = models.ForeignKey(Material, on_delete=models.PROTECT, verbose_name='자재')
    quantity       = models.IntegerField('재고수량', default=0)
    updated_at     = models.DateTimeField('갱신일시', auto_now=True)

    class Meta:
        db_table = 'center_inventory'
        verbose_name = '센터 재고'
        unique_together = [['support_center', 'material']]

    def __str__(self):
        return f'{self.support_center.name} - {self.material.name}: {self.quantity}'


class WorkerInventory(models.Model):
    """기사 보유 자재"""
    worker   = models.ForeignKey('accounts.User', on_delete=models.CASCADE, verbose_name='기사')
    material = models.ForeignKey(Material, on_delete=models.PROTECT, verbose_name='자재')
    quantity = models.IntegerField('보유수량', default=0)
    updated_at = models.DateTimeField('갱신일시', auto_now=True)

    class Meta:
        db_table = 'worker_inventory'
        verbose_name = '기사 보유 자재'
        unique_together = [['worker', 'material']]


class MaterialInbound(models.Model):
    """자재 입고 (창고)"""
    INBOUND_TYPE_CHOICES = [
        ('normal', '일반 입고'),
        ('return', '반납 입고'),
    ]
    INBOUND_NUMBER_PREFIX = 'IN'
    inbound_number = models.CharField('입고번호', max_length=30, unique=True, db_index=True)
    material       = models.ForeignKey(Material, on_delete=models.PROTECT, verbose_name='자재')
    quantity       = models.PositiveIntegerField('입고수량')
    unit_price       = models.DecimalField('단가', max_digits=10, decimal_places=0, default=0)
    inbound_type     = models.CharField('입고유형', max_length=10, choices=INBOUND_TYPE_CHOICES, default='normal')
    from_center      = models.ForeignKey('schools.SupportCenter', on_delete=models.SET_NULL,
                                         null=True, blank=True, verbose_name='반납 센터',
                                         related_name='material_inbound_from')
    supplier         = models.CharField('공급업체', max_length=100, blank=True)
    handover_person  = models.CharField('인계자', max_length=50, blank=True)
    receiver_person  = models.CharField('인수자', max_length=50, blank=True)
    inbound_date     = models.DateField('입고일')
    received_by      = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, verbose_name='입고담당자')
    note               = models.TextField('비고', blank=True)
    pdf_path           = models.CharField('입고증PDF경로', max_length=500, blank=True)
    signature_data     = models.TextField('전자서명(구)', blank=True)
    handover_signature = models.TextField('인계자서명', blank=True)
    receiver_signature = models.TextField('인수자서명', blank=True)
    handover_phone     = models.CharField('인계자연락처', max_length=20, blank=True)
    receiver_phone     = models.CharField('인수자연락처', max_length=20, blank=True)
    created_at         = models.DateTimeField('등록일시', auto_now_add=True)

    class Meta:
        db_table = 'material_inbound'
        verbose_name = '자재 입고'
        verbose_name_plural = '자재 입고 목록'
        ordering = ['-inbound_date']

    def __str__(self):
        return f'{self.inbound_number} - {self.material.name} {self.quantity}'

    @classmethod
    def generate_number(cls, inbound_date=None):
        if inbound_date is None:
            inbound_date = timezone.localdate()
        date_str = inbound_date.strftime('%Y%m%d')
        count = cls.objects.filter(inbound_number__startswith=f'{cls.INBOUND_NUMBER_PREFIX}{date_str}').count()
        return f'{cls.INBOUND_NUMBER_PREFIX}{date_str}_{str(count + 1).zfill(3)}'


class MaterialOutbound(models.Model):
    """자재 출고 (창고 → 지원청)"""
    outbound_number  = models.CharField('출고번호', max_length=30, unique=True, db_index=True)
    material         = models.ForeignKey(Material, on_delete=models.PROTECT, verbose_name='자재')
    quantity         = models.PositiveIntegerField('출고수량')
    from_warehouse   = models.BooleanField('창고출고', default=True)
    from_center      = models.ForeignKey('schools.SupportCenter', on_delete=models.SET_NULL,
                                         null=True, blank=True, verbose_name='출고 센터',
                                         related_name='material_outbound_from')
    to_center        = models.ForeignKey('schools.SupportCenter', on_delete=models.PROTECT,
                                         verbose_name='수령 지원청', null=True, blank=True)
    to_worker        = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
                                         verbose_name='수령 기사', related_name='material_outbounds')
    to_school        = models.CharField('출고 학교', max_length=100, blank=True)
    outbound_date    = models.DateField('출고일')
    issued_by        = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True,
                                         verbose_name='출고담당자', related_name='issued_outbounds')
    handover_person  = models.CharField('인계자', max_length=50, blank=True)
    receiver_person  = models.CharField('인수자', max_length=50, blank=True)
    note               = models.TextField('비고', blank=True)
    pdf_path           = models.CharField('출고증PDF경로', max_length=500, blank=True)
    signature_data     = models.TextField('전자서명(구)', blank=True)
    handover_signature = models.TextField('인계자서명', blank=True)
    receiver_signature = models.TextField('인수자서명', blank=True)
    handover_phone     = models.CharField('인계자연락처', max_length=20, blank=True)
    receiver_phone     = models.CharField('인수자연락처', max_length=20, blank=True)
    created_at         = models.DateTimeField('등록일시', auto_now_add=True)

    @classmethod
    def generate_number(cls, outbound_date=None):
        if outbound_date is None:
            outbound_date = timezone.localdate()
        date_str = outbound_date.strftime('%Y%m%d')
        count = cls.objects.filter(outbound_number__startswith=f'OUT{date_str}').count()
        return f'OUT{date_str}_{str(count + 1).zfill(3)}'

    class Meta:
        db_table = 'material_outbound'
        verbose_name = '자재 출고'
        verbose_name_plural = '자재 출고 목록'
        ordering = ['-outbound_date']


class MaterialTransfer(models.Model):
    """센터 간 자재 이동"""
    material      = models.ForeignKey(Material, on_delete=models.PROTECT, verbose_name='자재')
    quantity      = models.PositiveIntegerField('이동수량')
    from_center   = models.ForeignKey('schools.SupportCenter', on_delete=models.PROTECT,
                                      verbose_name='출발 센터', related_name='transfer_out')
    to_center     = models.ForeignKey('schools.SupportCenter', on_delete=models.PROTECT,
                                      verbose_name='도착 센터', related_name='transfer_in')
    transfer_date = models.DateField('이동일')
    note          = models.TextField('비고', blank=True)
    created_at    = models.DateTimeField('등록일시', auto_now_add=True)

    class Meta:
        db_table = 'material_transfer'
        verbose_name = '자재 이동'
        ordering = ['-transfer_date']


class MaterialUsage(models.Model):
    """자재 사용 기록 (학교 현장)"""
    material  = models.ForeignKey(Material, on_delete=models.PROTECT, verbose_name='자재')
    quantity  = models.PositiveIntegerField('사용수량')
    school    = models.ForeignKey('schools.School', on_delete=models.PROTECT, verbose_name='학교')
    worker    = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, verbose_name='사용기사')
    incident  = models.ForeignKey('incidents.Incident', on_delete=models.SET_NULL, null=True, blank=True,
                                  verbose_name='관련장애')
    used_date = models.DateField('사용일')
    note      = models.TextField('비고', blank=True)
    created_at= models.DateTimeField('등록일시', auto_now_add=True)

    class Meta:
        db_table = 'material_usage'
        verbose_name = '자재 사용'
        ordering = ['-used_date']


class MaterialReturn(models.Model):
    """잔여 자재 반납 (현장→센터 반납 입고)"""
    return_number    = models.CharField('반납번호', max_length=30, unique=True, db_index=True, blank=True)
    material         = models.ForeignKey(Material, on_delete=models.PROTECT, verbose_name='자재')
    quantity         = models.PositiveIntegerField('반납수량')
    from_worker      = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='반납기사')
    from_school      = models.CharField('반납 출처(학교)', max_length=100, blank=True)
    to_center        = models.ForeignKey('schools.SupportCenter', on_delete=models.PROTECT, verbose_name='반납 센터')
    return_date      = models.DateField('반납일')
    received_by      = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
                                         verbose_name='수령담당자', related_name='received_returns')
    handover_person  = models.CharField('인계자', max_length=50, blank=True)
    receiver_person  = models.CharField('인수자', max_length=50, blank=True)
    handover_phone   = models.CharField('인계자연락처', max_length=20, blank=True)
    receiver_phone   = models.CharField('인수자연락처', max_length=20, blank=True)
    note             = models.TextField('비고', blank=True)
    created_at       = models.DateTimeField('등록일시', auto_now_add=True)

    class Meta:
        db_table = 'material_return'
        verbose_name = '자재 반납'
        ordering = ['-return_date']

    @classmethod
    def generate_number(cls, return_date=None):
        from django.utils import timezone as tz
        if return_date is None:
            return_date = tz.localdate()
        date_str = return_date.strftime('%Y%m%d')
        count = cls.objects.filter(return_number__startswith=f'RET{date_str}').count()
        return f'RET{date_str}_{str(count + 1).zfill(3)}'


class MaterialUsageStats(models.Model):
    """자재 사용 통계 (AI 예측용)"""
    material  = models.ForeignKey(Material, on_delete=models.CASCADE, verbose_name='자재')
    period    = models.CharField('기간', max_length=7, help_text='YYYY-MM')
    used_qty  = models.IntegerField('사용수량', default=0)
    created_at= models.DateTimeField('생성일시', auto_now_add=True)

    class Meta:
        db_table = 'material_usage_stats'
        verbose_name = '자재 사용 통계'
        unique_together = [['material', 'period']]


class MaterialForecast(models.Model):
    """자재 수요 예측 (AI)"""
    material      = models.ForeignKey(Material, on_delete=models.CASCADE, verbose_name='자재')
    forecast_month= models.CharField('예측월', max_length=7, help_text='YYYY-MM')
    predicted_qty = models.IntegerField('예측수량')
    confidence    = models.FloatField('신뢰도', default=0.0)
    created_at    = models.DateTimeField('생성일시', auto_now_add=True)

    class Meta:
        db_table = 'material_forecast'
        verbose_name = '자재 수요 예측'
        unique_together = [['material', 'forecast_month']]
