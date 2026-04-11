"""
assets 앱 모델
장비 관리 (스위치 C3100-24TL 987대 창고 포함, RMA, 이력 추적)
교육청 제공 장비 전체 관리: 창고 → 센터 → 학교 흐름
"""
from django.db import models
from django.utils import timezone

# ── 사업 목록 (전체 공통 상수) ──────────────────────────────
PROJECT_CHOICES = [
    ('2024년 학교정보화지원체계(테크센터) 운영지원사업(강북권)', '2024년 강북'),
    ('2024년 학교정보화지원체계(테크센터) 운영지원사업(강남권)', '2024년 강남'),
    ('2025년 학교정보화지원체계(테크센터) 운영지원사업',         '2025년'),
    ('2026년 학교 디지털 인프라 통합관리(테크센터) 운영',        '2026년'),
    ('2025년 교육지원청',  '2025년 교육지원청'),
    ('2026년 교육지원청',  '2026년 교육지원청'),
    ('2025년 테크매니져',  '2025년 테크매니져'),
]
# 센터→학교 신규 설치 시 자동 적용되는 현재 사업
CURRENT_INSTALL_PROJECT = '2026년 학교 디지털 인프라 통합관리(테크센터) 운영'
CURRENT_INSTALL_YEAR    = 2026


class AssetCategory(models.Model):
    """장비 분류"""
    CATEGORY_CHOICES = [
        ('switch',     '스위치'),
        ('poe_switch', 'PoE 스위치'),
        ('ap',         '무선 AP'),
        ('router',     '라우터'),
        ('server',     '서버'),
        ('other',      '기타'),
    ]
    code         = models.CharField('코드', max_length=20, unique=True, choices=CATEGORY_CHOICES)
    name         = models.CharField('분류명', max_length=50)
    usable_years = models.PositiveSmallIntegerField('내용연수(년)', default=5)
    order        = models.PositiveSmallIntegerField('정렬순서', default=0)

    class Meta:
        db_table = 'asset_categories'
        verbose_name = '장비 분류'
        ordering = ['order']

    def __str__(self):
        return self.name


class AssetModel(models.Model):
    """장비 모델 마스터"""
    category     = models.ForeignKey(AssetCategory, on_delete=models.PROTECT, verbose_name='분류')
    manufacturer = models.CharField('제조사', max_length=100)
    model_name   = models.CharField('모델명', max_length=100)
    spec         = models.TextField('사양', blank=True)
    usable_years = models.PositiveSmallIntegerField('내용연수(년)', default=5)
    is_active    = models.BooleanField('활성', default=True)
    note         = models.TextField('비고', blank=True)

    class Meta:
        db_table = 'asset_models'
        verbose_name = '장비 모델'
        unique_together = [['manufacturer', 'model_name']]

    def __str__(self):
        return f'{self.manufacturer} {self.model_name}'


class Asset(models.Model):
    """
    장비 자산 (개별 장비)
    상태 흐름: warehouse → center → installed
              installed → center(회수) → warehouse → rma → warehouse(반환)
    """
    STATUS_CHOICES = [
        ('warehouse',  '창고 보관'),
        ('center',     '센터 보관'),
        ('installed',  '학교 설치'),
        ('edu_office', '교육지원청 설치'),
        ('rma',        'RMA 진행'),
        ('disposed',   '폐기'),
        ('returned',   '교육청 반납'),
    ]

    asset_model    = models.ForeignKey(AssetModel, on_delete=models.PROTECT, verbose_name='장비 모델')
    serial_number  = models.CharField('제조번호(S/N)', max_length=100, unique=True, db_index=True)
    asset_tag      = models.CharField('관리번호', max_length=50, unique=True,
                                      null=True, blank=True,
                                      help_text='스티커 부착 관리번호 (향후 일괄 부여)')
    status         = models.CharField('상태', max_length=20, choices=STATUS_CHOICES, default='warehouse')

    # 현재 위치
    current_center  = models.ForeignKey('schools.SupportCenter', on_delete=models.SET_NULL,
                                        null=True, blank=True, verbose_name='현재 센터')
    current_school  = models.ForeignKey('schools.School', on_delete=models.SET_NULL,
                                        null=True, blank=True, verbose_name='설치 학교')
    install_location = models.CharField('설치 위치', max_length=200, blank=True,
                                         help_text='예: 전산실 랙 2번째 칸')

    # 사업 정보 (설치 연도 + 사업명으로 장비 관리)
    install_year    = models.PositiveSmallIntegerField(
        '설치 연도(사업년도)', null=True, blank=True,
        help_text='예: 2023 (사업 기준 연도)'
    )
    project_name    = models.CharField(
        '사업명', max_length=200, blank=True,
        help_text='예: 디지털교육환경 구축사업, 기가인터넷 고도화 사업'
    )

    # 날짜
    purchased_at    = models.DateField('구매일', null=True, blank=True)
    installed_at    = models.DateField('설치일', null=True, blank=True)
    warranty_expire = models.DateField('보증만료일', null=True, blank=True)
    disposed_at     = models.DateField('폐기일', null=True, blank=True)

    # RMA 교체품 특별관리
    is_rma_replaced = models.BooleanField('RMA 교체품 여부', default=False,
                                          help_text='RMA 수리불가로 S/N이 변경된 교체품')
    replaced_from   = models.ForeignKey('self', on_delete=models.SET_NULL,
                                        null=True, blank=True,
                                        related_name='replacement_assets',
                                        verbose_name='원본 장비(RMA 교체 전)')

    note       = models.TextField('비고', blank=True)
    created_at = models.DateTimeField('등록일시', auto_now_add=True)
    updated_at = models.DateTimeField('수정일시', auto_now=True)

    class Meta:
        db_table = 'assets'
        verbose_name = '장비'
        verbose_name_plural = '장비 목록'
        ordering = ['asset_model', 'serial_number']
        indexes = [
            models.Index(fields=['status', 'current_school']),
            models.Index(fields=['status', 'current_center']),
            models.Index(fields=['is_rma_replaced']),
            models.Index(fields=['install_year', 'project_name']),
        ]

    def __str__(self):
        return f'{self.asset_model} S/N:{self.serial_number}'


class AssetInbound(models.Model):
    """
    장비 입고
    - 교육청 → 창고 (신규 장비 입고)
    - 제조사 → 창고 (RMA 반환)
    - 학교 → 센터 (회수 후 센터 보관) — AssetReturn과 병행 사용 가능
    """
    FROM_TYPE_CHOICES = [
        ('education_office', '교육청'),
        ('vendor',           '제조사(RMA반환)'),
        ('school',           '학교(회수)'),
        ('center',           '센터'),
        ('other',            '기타'),
    ]
    TO_TYPE_CHOICES = [
        ('warehouse', '창고'),
        ('center',    '센터'),
    ]

    inbound_number     = models.CharField('입고번호', max_length=30, unique=True, db_index=True)
    asset              = models.ForeignKey(Asset, on_delete=models.PROTECT,
                                           verbose_name='장비', related_name='inbounds')

    # 출처
    from_location_type = models.CharField('출처 구분', max_length=30,
                                           choices=FROM_TYPE_CHOICES, default='education_office')
    from_center        = models.ForeignKey('schools.SupportCenter', on_delete=models.SET_NULL,
                                           null=True, blank=True, verbose_name='출처 센터',
                                           related_name='asset_inbound_from')
    from_location_name = models.CharField('출처 명칭', max_length=200, blank=True,
                                          help_text='교육청명, 학교명, 제조사명 등')

    # 입고 목적지
    to_location_type   = models.CharField('입고 목적지', max_length=20,
                                           choices=TO_TYPE_CHOICES, default='warehouse')
    to_center          = models.ForeignKey('schools.SupportCenter', on_delete=models.SET_NULL,
                                           null=True, blank=True, verbose_name='입고 센터',
                                           related_name='asset_inbound_to')

    inbound_date       = models.DateField('입고일')
    received_by        = models.ForeignKey('accounts.User', on_delete=models.SET_NULL,
                                           null=True, verbose_name='입고담당자',
                                           related_name='asset_inbounds_received')

    # 인계/인수 정보 (자재관리와 동일 구조)
    handover_person    = models.CharField('인계자명', max_length=50, blank=True)
    handover_phone     = models.CharField('인계자연락처', max_length=20, blank=True)
    handover_signature = models.TextField('인계자서명', blank=True)
    receiver_person    = models.CharField('인수자명', max_length=50, blank=True)
    receiver_phone     = models.CharField('인수자연락처', max_length=20, blank=True)
    receiver_signature = models.TextField('인수자서명', blank=True)

    note      = models.TextField('비고', blank=True)
    pdf_path  = models.CharField('입고증PDF경로', max_length=500, blank=True)
    created_at = models.DateTimeField('등록일시', auto_now_add=True)

    class Meta:
        db_table = 'asset_inbound'
        verbose_name = '장비 입고'
        ordering = ['-inbound_date', '-created_at']

    @classmethod
    def generate_number(cls, date=None):
        if date is None:
            date = timezone.localdate()
        date_str = date.strftime('%Y%m%d')
        count = cls.objects.filter(inbound_number__startswith=f'ASIN{date_str}').count()
        return f'ASIN{date_str}_{str(count + 1).zfill(3)}'

    def __str__(self):
        return self.inbound_number


class AssetOutbound(models.Model):
    """
    장비 출고
    - 창고 → 센터 (관리자만)
    - 센터 → 학교 (일반사용자도 가능)
    - 창고/센터 → 제조사 (RMA 발송)
    """
    FROM_TYPE_CHOICES = [
        ('warehouse', '창고'),
        ('center',    '센터'),
    ]
    TO_TYPE_CHOICES = [
        ('center',  '센터'),
        ('school',  '학교'),
        ('vendor',  '제조사(RMA발송)'),
    ]

    outbound_number    = models.CharField('출고번호', max_length=30, unique=True, db_index=True)
    asset              = models.ForeignKey(Asset, on_delete=models.PROTECT,
                                           verbose_name='장비', related_name='outbounds')

    # 출발지
    from_location_type = models.CharField('출고 출처', max_length=20,
                                           choices=FROM_TYPE_CHOICES, default='warehouse')
    from_center        = models.ForeignKey('schools.SupportCenter', on_delete=models.SET_NULL,
                                           null=True, blank=True, verbose_name='출고 센터',
                                           related_name='asset_outbound_from')

    # 목적지
    to_location_type   = models.CharField('출고 목적지', max_length=20,
                                           choices=TO_TYPE_CHOICES, default='center')
    to_center          = models.ForeignKey('schools.SupportCenter', on_delete=models.SET_NULL,
                                           null=True, blank=True, verbose_name='수령 센터',
                                           related_name='asset_outbound_to')
    to_school          = models.ForeignKey('schools.School', on_delete=models.SET_NULL,
                                           null=True, blank=True, verbose_name='설치 학교')

    outbound_date      = models.DateField('출고일')
    issued_by          = models.ForeignKey('accounts.User', on_delete=models.SET_NULL,
                                           null=True, verbose_name='출고담당자',
                                           related_name='asset_outbounds_issued')

    # 인계/인수 정보
    handover_person    = models.CharField('인계자명', max_length=50, blank=True)
    handover_phone     = models.CharField('인계자연락처', max_length=20, blank=True)
    handover_signature = models.TextField('인계자서명', blank=True)
    receiver_person    = models.CharField('인수자명', max_length=50, blank=True)
    receiver_phone     = models.CharField('인수자연락처', max_length=20, blank=True)
    receiver_signature = models.TextField('인수자서명', blank=True)

    note      = models.TextField('비고', blank=True)
    pdf_path  = models.CharField('출고증PDF경로', max_length=500, blank=True)
    created_at = models.DateTimeField('등록일시', auto_now_add=True)

    class Meta:
        db_table = 'asset_outbound'
        verbose_name = '장비 출고'
        ordering = ['-outbound_date', '-created_at']

    @classmethod
    def generate_number(cls, date=None):
        if date is None:
            date = timezone.localdate()
        date_str = date.strftime('%Y%m%d')
        count = cls.objects.filter(outbound_number__startswith=f'ASOUT{date_str}').count()
        return f'ASOUT{date_str}_{str(count + 1).zfill(3)}'

    def __str__(self):
        return self.outbound_number


class AssetReturn(models.Model):
    """
    장비 반납/회수
    - 학교 → 센터 (고장 회수)
    - 센터 → 창고 (잉여 반납)
    """
    FROM_TYPE_CHOICES = [
        ('school',  '학교'),
        ('center',  '센터'),
    ]
    TO_TYPE_CHOICES = [
        ('center',    '센터'),
        ('warehouse', '창고'),
    ]

    return_number      = models.CharField('반납번호', max_length=30, unique=True, db_index=True)
    asset              = models.ForeignKey(Asset, on_delete=models.PROTECT,
                                           verbose_name='장비', related_name='returns')

    # 반납 출처
    from_location_type = models.CharField('반납 출처', max_length=20,
                                           choices=FROM_TYPE_CHOICES, default='school')
    from_school        = models.ForeignKey('schools.School', on_delete=models.SET_NULL,
                                           null=True, blank=True, verbose_name='반납 학교',
                                           related_name='asset_returns_from_school')
    from_center        = models.ForeignKey('schools.SupportCenter', on_delete=models.SET_NULL,
                                           null=True, blank=True, verbose_name='반납 센터',
                                           related_name='asset_returns_from_center')

    # 반납 목적지
    to_location_type   = models.CharField('반납 목적지', max_length=20,
                                           choices=TO_TYPE_CHOICES, default='center')
    to_center          = models.ForeignKey('schools.SupportCenter', on_delete=models.SET_NULL,
                                           null=True, blank=True, verbose_name='수령 센터',
                                           related_name='asset_returns_to_center')

    return_date        = models.DateField('반납일')
    received_by        = models.ForeignKey('accounts.User', on_delete=models.SET_NULL,
                                           null=True, blank=True, verbose_name='수령담당자',
                                           related_name='asset_returns_received')
    reason             = models.CharField('반납 사유', max_length=200, blank=True,
                                          help_text='고장, 교체, 잉여 등')

    # 인계/인수 정보
    handover_person    = models.CharField('인계자명', max_length=50, blank=True)
    handover_phone     = models.CharField('인계자연락처', max_length=20, blank=True)
    handover_signature = models.TextField('인계자서명', blank=True)
    receiver_person    = models.CharField('인수자명', max_length=50, blank=True)
    receiver_phone     = models.CharField('인수자연락처', max_length=20, blank=True)
    receiver_signature = models.TextField('인수자서명', blank=True)

    note      = models.TextField('비고', blank=True)
    pdf_path  = models.CharField('반납증PDF경로', max_length=500, blank=True)
    created_at = models.DateTimeField('등록일시', auto_now_add=True)

    class Meta:
        db_table = 'asset_returns'
        verbose_name = '장비 반납/회수'
        ordering = ['-return_date', '-created_at']

    @classmethod
    def generate_number(cls, date=None):
        if date is None:
            date = timezone.localdate()
        date_str = date.strftime('%Y%m%d')
        count = cls.objects.filter(return_number__startswith=f'ASRET{date_str}').count()
        return f'ASRET{date_str}_{str(count + 1).zfill(3)}'

    def __str__(self):
        return self.return_number


class AssetHistory(models.Model):
    """
    장비 이력 추적
    모든 이동/작업 시 자동 기록
    """
    ACTION_CHOICES = [
        ('inbound',      '입고'),
        ('outbound',     '출고'),
        ('install',      '설치'),
        ('return',       '반납/회수'),
        ('replace',      '교체'),
        ('rma_send',     'RMA 발송'),
        ('rma_return',   'RMA 반환(수리)'),
        ('rma_replaced', 'RMA 교체품 수령'),
        ('dispose',      '폐기'),
        ('tag',          '관리번호 부여'),
        ('edit',         '정보 수정'),
    ]

    asset         = models.ForeignKey(Asset, on_delete=models.CASCADE,
                                       verbose_name='장비', related_name='history')
    action        = models.CharField('작업유형', max_length=20, choices=ACTION_CHOICES)
    from_location = models.CharField('이전위치', max_length=200, blank=True)
    to_location   = models.CharField('이후위치', max_length=200, blank=True)
    worker        = models.ForeignKey('accounts.User', on_delete=models.SET_NULL,
                                       null=True, verbose_name='작업자')
    note          = models.TextField('비고', blank=True)
    occurred_at   = models.DateTimeField('발생일시', auto_now_add=True)

    class Meta:
        db_table = 'asset_history'
        verbose_name = '장비 이력'
        ordering = ['-occurred_at']

    def __str__(self):
        return f'{self.asset.serial_number} - {self.get_action_display()}'


class AssetRMA(models.Model):
    """
    RMA (반품/수리) 관리
    수리불가로 S/N 변경 교체품이 오는 경우: replacement_asset 연결
    """
    STATUS_CHOICES = [
        ('sent',     'RMA 발송'),
        ('received', '제조사 수령'),
        ('repaired', '수리 완료'),
        ('returned', '반환 완료(동일 S/N)'),
        ('replaced', '교체품 수령(S/N 변경)'),
    ]

    asset             = models.ForeignKey(Asset, on_delete=models.PROTECT,
                                           verbose_name='발송 장비', related_name='rma_records')
    rma_number        = models.CharField('RMA번호', max_length=100, blank=True)
    status            = models.CharField('상태', max_length=20,
                                          choices=STATUS_CHOICES, default='sent')
    reason            = models.TextField('RMA 사유')
    sent_date         = models.DateField('발송일', null=True, blank=True)
    returned_date     = models.DateField('반환일', null=True, blank=True)
    handled_by        = models.ForeignKey('accounts.User', on_delete=models.SET_NULL,
                                           null=True, verbose_name='담당자')

    # 교체품 관리 (S/N 변경 시)
    new_serial        = models.CharField('교체 후 S/N', max_length=100, blank=True)
    replacement_asset = models.OneToOneField(Asset, on_delete=models.SET_NULL,
                                              null=True, blank=True,
                                              related_name='original_rma',
                                              verbose_name='교체품 장비(is_rma_replaced=True)')

    note       = models.TextField('비고', blank=True)
    created_at = models.DateTimeField('등록일시', auto_now_add=True)

    class Meta:
        db_table = 'asset_rma'
        verbose_name = 'RMA 관리'
        ordering = ['-created_at']

    def __str__(self):
        return f'RMA-{self.asset.serial_number} ({self.get_status_display()})'


class DeviceNetworkConfig(models.Model):
    """
    장비별 개별 네트워크 설정 (1:1 with Asset)
    모델 표준 설정(AssetModelConfig)을 적용받거나 개별 오버라이드
    """
    asset          = models.OneToOneField(Asset, on_delete=models.CASCADE,
                                          related_name='network_config', verbose_name='장비')
    mgmt_ip        = models.GenericIPAddressField('관리 IP', null=True, blank=True)
    mgmt_subnet    = models.CharField('서브넷 마스크', max_length=20, blank=True,
                                       default='255.255.255.0')
    mgmt_gateway   = models.GenericIPAddressField('게이트웨이', null=True, blank=True)
    vlan_mgmt      = models.PositiveSmallIntegerField('관리 VLAN', null=True, blank=True)
    vlan_data      = models.CharField('데이터 VLAN 목록', max_length=200, blank=True,
                                       help_text='예: 10,20,30')
    uplink_port    = models.CharField('업링크 포트', max_length=50, blank=True,
                                       help_text='예: GE1/0/1')
    uplink_speed   = models.CharField('업링크 속도', max_length=30, blank=True,
                                       help_text='예: 1Gbps')
    ssh_enabled    = models.BooleanField('SSH 활성', default=True)
    snmp_community = models.CharField('SNMP Community', max_length=100, blank=True)
    firmware_ver   = models.CharField('펌웨어 버전', max_length=100, blank=True)
    last_config_backup = models.DateTimeField('마지막 설정 백업', null=True, blank=True)
    config_note    = models.TextField('설정 메모', blank=True)
    updated_at     = models.DateTimeField('수정일시', auto_now=True)

    class Meta:
        db_table = 'asset_network_configs'
        verbose_name = '장비 네트워크 설정'

    def __str__(self):
        return f'{self.asset.serial_number} - {self.mgmt_ip or "IP미설정"}'


class AssetModelConfig(models.Model):
    """
    장비 모델별 표준 네트워크 설정
    - 별도 네비게이션 탭 "장비 설정"에서 관리
    - 모델 선택 후 설정값 입력 → 해당 모델 전체 장비에 일괄 적용 가능
    - 우선 개발: 코어엣지 C3100-24TL
    - 향후: 학교 설치 장비 모델 파악 후 계속 추가
    """
    asset_model     = models.OneToOneField(AssetModel, on_delete=models.CASCADE,
                                            related_name='model_config', verbose_name='장비 모델')
    vlan_mgmt       = models.PositiveSmallIntegerField('관리 VLAN', null=True, blank=True)
    vlan_data       = models.CharField('데이터 VLAN 목록', max_length=200, blank=True,
                                        help_text='예: 10,20,30')
    uplink_port     = models.CharField('업링크 포트', max_length=50, blank=True)
    uplink_speed    = models.CharField('업링크 속도', max_length=30, blank=True)
    ssh_enabled     = models.BooleanField('SSH 활성', default=True)
    snmp_community  = models.CharField('SNMP Community', max_length=100, blank=True)
    firmware_ver    = models.CharField('표준 펌웨어 버전', max_length=100, blank=True)
    config_commands = models.TextField('설정 CLI 명령어', blank=True,
                                        help_text='향후 장비 자동 설정 투입용 CLI 명령어 (C3100-24TL 등)')
    config_note     = models.TextField('설정 메모', blank=True)
    updated_at      = models.DateTimeField('수정일시', auto_now=True)
    updated_by      = models.ForeignKey('accounts.User', on_delete=models.SET_NULL,
                                         null=True, blank=True, verbose_name='최종수정자')

    class Meta:
        db_table = 'asset_model_configs'
        verbose_name = '장비 모델 표준 설정'

    def __str__(self):
        return f'{self.asset_model} 표준설정'
