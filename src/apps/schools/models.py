"""
schools 앱 모델
지원청, 학교, 건물, 층, 교실 관리 (GIS 연동)
"""
from django.db import models


class SupportCenter(models.Model):
    """11개 교육지원청"""
    CENTER_CHOICES = [
        ('dongbu',    '동부'),
        ('seobu',     '서부'),
        ('nambu',     '남부'),
        ('bukbu',     '북부'),
        ('jungbu',    '중부'),
        ('gangdong',  '강동송파'),
        ('gangseo',   '강서양천'),
        ('gangnam',   '강남서초'),
        ('dongjak',   '동작관악'),
        ('seongdong', '성동광진'),
        ('seongbuk',  '성북강북'),
    ]
    code       = models.CharField('코드', max_length=20, unique=True, choices=CENTER_CHOICES)
    name       = models.CharField('지원청명', max_length=50)
    address    = models.TextField('주소', blank=True)
    phone      = models.CharField('연락처', max_length=20, blank=True)
    lat        = models.DecimalField('위도', max_digits=10, decimal_places=7, null=True, blank=True)
    lng        = models.DecimalField('경도', max_digits=10, decimal_places=7, null=True, blank=True)
    url        = models.URLField('홈페이지', blank=True)
    is_active  = models.BooleanField('활성', default=True)

    class Meta:
        db_table = 'support_centers'
        verbose_name = '교육지원청'
        verbose_name_plural = '교육지원청 목록'
        ordering = ['id']

    def __str__(self):
        return self.name


class SchoolType(models.Model):
    """학제 구분"""
    TYPE_CHOICES = [
        ('kindergarten',  '유치원'),
        ('elementary',    '초등학교'),
        ('middle',        '중학교'),
        ('high',          '고등학교'),
        ('special',       '특수학교'),
        ('etc',           '각종학교'),
        ('vocational',    '고등기술학교'),
    ]
    code  = models.CharField('코드', max_length=20, unique=True, choices=TYPE_CHOICES)
    name  = models.CharField('학제명', max_length=30)
    order = models.PositiveSmallIntegerField('정렬순서', default=0)

    class Meta:
        db_table = 'school_types'
        verbose_name = '학제'
        verbose_name_plural = '학제 목록'
        ordering = ['order']

    def __str__(self):
        return self.name


class School(models.Model):
    """학교 정보 (1411개)"""
    support_center = models.ForeignKey(SupportCenter, on_delete=models.PROTECT, verbose_name='교육지원청', related_name='schools')
    school_type    = models.ForeignKey(SchoolType, on_delete=models.PROTECT, verbose_name='학제', related_name='schools')
    name           = models.CharField('학교명', max_length=100)
    code           = models.CharField('학교코드', max_length=20, blank=True, db_index=True)
    address        = models.TextField('주소')
    zip_code       = models.CharField('우편번호', max_length=10, blank=True)
    lat            = models.DecimalField('위도', max_digits=10, decimal_places=7, null=True, blank=True)
    lng            = models.DecimalField('경도', max_digits=10, decimal_places=7, null=True, blank=True)
    phone          = models.CharField('학교 대표전화', max_length=20, blank=True)
    fax            = models.CharField('팩스', max_length=20, blank=True)
    homepage       = models.URLField('홈페이지', blank=True)
    principal_name = models.CharField('교장명', max_length=30, blank=True)
    is_active      = models.BooleanField('활성', default=True)
    nas_folder_created = models.BooleanField('NAS폴더생성', default=False)
    created_at     = models.DateTimeField('등록일시', auto_now_add=True)
    updated_at     = models.DateTimeField('수정일시', auto_now=True)

    class Meta:
        db_table = 'schools'
        verbose_name = '학교'
        verbose_name_plural = '학교 목록'
        ordering = ['support_center', 'school_type', 'name']
        unique_together = [['support_center', 'name']]

    def __str__(self):
        return f'{self.support_center.name} {self.school_type.name} {self.name}'


class SchoolContact(models.Model):
    """학교 담당자 (장애접수 시 자동 불러오기)"""
    school     = models.ForeignKey(School, on_delete=models.CASCADE, verbose_name='학교', related_name='contacts')
    name       = models.CharField('담당자명', max_length=50)
    phone      = models.CharField('연락처', max_length=20)
    position   = models.CharField('직책', max_length=50, blank=True)
    email      = models.EmailField('이메일', blank=True)
    is_primary = models.BooleanField('주담당자', default=False)
    created_at = models.DateTimeField('등록일시', auto_now_add=True)

    class Meta:
        db_table = 'school_contacts'
        verbose_name = '학교 담당자'
        verbose_name_plural = '학교 담당자 목록'

    def __str__(self):
        return f'{self.school.name} - {self.name}'


class SchoolBuilding(models.Model):
    """학교 건물"""
    BUILDING_CHOICES = [
        ('main',  '본관'),
        ('annex', '별관'),
        ('east',  '동관'),
        ('west',  '서관'),
        ('other', '기타'),
    ]
    school     = models.ForeignKey(School, on_delete=models.CASCADE, verbose_name='학교', related_name='buildings')
    name       = models.CharField('건물명', max_length=50)
    code       = models.CharField('건물코드', max_length=20, blank=True)
    floors     = models.PositiveSmallIntegerField('층수', default=4)
    basement   = models.PositiveSmallIntegerField('지하층수', default=0)
    note       = models.TextField('비고', blank=True)
    order      = models.PositiveSmallIntegerField('정렬순서', default=0)

    class Meta:
        db_table = 'school_buildings'
        verbose_name = '학교 건물'
        verbose_name_plural = '학교 건물 목록'
        ordering = ['school', 'order']

    def __str__(self):
        return f'{self.school.name} - {self.name}'


class SchoolFloor(models.Model):
    """건물 층"""
    building   = models.ForeignKey(SchoolBuilding, on_delete=models.CASCADE, verbose_name='건물', related_name='floor_list')
    floor_num  = models.SmallIntegerField('층번호')   # 음수 = 지하
    floor_name = models.CharField('층이름', max_length=20)  # 예: 1층, 지하1층

    class Meta:
        db_table = 'school_floors'
        verbose_name = '건물 층'
        verbose_name_plural = '건물 층 목록'
        ordering = ['building', '-floor_num']

    def __str__(self):
        return f'{self.building} - {self.floor_name}'


class SchoolRoom(models.Model):
    """교실/공간 (VSDX 파싱 데이터 포함)"""
    ROOM_CHOICES = [
        ('class',    '일반교실'),
        ('special',  '특별실'),
        ('office',   '교무·행정실'),
        ('support',  '지원공간'),
        ('toilet',   '화장실'),
        ('computer', '전산실'),
        ('gym',      '체육관'),
        ('other',    '기타'),
    ]
    floor       = models.ForeignKey(SchoolFloor, on_delete=models.CASCADE, verbose_name='층', related_name='rooms')
    name        = models.CharField('교실명', max_length=100)
    room_number = models.CharField('호실번호', max_length=20, blank=True, db_index=True)
    room_type   = models.CharField('교실유형', max_length=20, choices=ROOM_CHOICES, default='other')
    area_m2     = models.DecimalField('면적(㎡)', max_digits=12, decimal_places=2, null=True, blank=True)
    # VSDX 좌표 (인치 단위, 평면도 렌더링용)
    pos_x       = models.DecimalField('X좌표', max_digits=10, decimal_places=4, null=True, blank=True)
    pos_y       = models.DecimalField('Y좌표', max_digits=10, decimal_places=4, null=True, blank=True)
    pos_w       = models.DecimalField('너비', max_digits=10, decimal_places=4, null=True, blank=True)
    pos_h       = models.DecimalField('높이', max_digits=10, decimal_places=4, null=True, blank=True)
    vsdx_source = models.CharField('VSDX 원본파일', max_length=200, blank=True)
    note        = models.TextField('비고', blank=True)

    class Meta:
        db_table = 'school_rooms'
        verbose_name = '교실/공간'
        verbose_name_plural = '교실/공간 목록'
        ordering = ['floor', 'room_number', 'name']

    def __str__(self):
        return f'{self.floor} - {self.room_number} {self.name}'


class VsdxImportLog(models.Model):
    """VSDX 파일 파싱 이력"""
    STATUS_CHOICES = [
        ('success', '성공'),
        ('fail',    '실패'),
        ('partial', '부분성공'),
    ]
    school      = models.ForeignKey(School, on_delete=models.CASCADE, verbose_name='학교',
                                    related_name='vsdx_logs', null=True, blank=True)
    file_name   = models.CharField('파일명', max_length=200)
    file_path   = models.CharField('파일경로', max_length=500)
    status      = models.CharField('결과', max_length=10, choices=STATUS_CHOICES, default='success')
    room_count  = models.PositiveIntegerField('파싱 호실수', default=0)
    error_msg   = models.TextField('오류내용', blank=True)
    imported_at = models.DateTimeField('처리일시', auto_now_add=True)

    class Meta:
        db_table = 'vsdx_import_logs'
        verbose_name = 'VSDX 임포트 로그'
        verbose_name_plural = 'VSDX 임포트 로그 목록'
        ordering = ['-imported_at']

    def __str__(self):
        return f'{self.file_name} ({self.status}) {self.imported_at:%Y-%m-%d %H:%M}'


class SchoolNetwork(models.Model):
    """학교 네트워크 정보"""
    school      = models.OneToOneField(School, on_delete=models.CASCADE, verbose_name='학교', related_name='network')
    ip_range    = models.CharField('IP 대역', max_length=50, blank=True, help_text='예: 10.1.1.0/24')
    gateway     = models.GenericIPAddressField('게이트웨이', null=True, blank=True)
    dns_primary = models.GenericIPAddressField('주 DNS', null=True, blank=True)
    dns_secondary = models.GenericIPAddressField('보조 DNS', null=True, blank=True)
    isp         = models.CharField('통신사', max_length=50, blank=True)
    bandwidth   = models.CharField('회선속도', max_length=20, blank=True, help_text='예: 1Gbps')
    vlan_info   = models.TextField('VLAN 정보', blank=True)
    snmp_community = models.CharField('SNMP Community', max_length=50, blank=True, default='public')
    updated_at  = models.DateTimeField('수정일시', auto_now=True)

    class Meta:
        db_table = 'school_networks'
        verbose_name = '학교 네트워크'
        verbose_name_plural = '학교 네트워크 목록'

    def __str__(self):
        return f'{self.school.name} - {self.ip_range}'


class SchoolEquipment(models.Model):
    """학교 네트워크 장비 인벤토리 (장비목록.xlsx 임포트)"""
    school           = models.ForeignKey(School, on_delete=models.CASCADE, verbose_name='학교', related_name='equipment_list')
    category         = models.CharField('구분', max_length=30, db_index=True)
    model_name       = models.CharField('모델명', max_length=100, blank=True)
    manufacturer     = models.CharField('제조사', max_length=100, blank=True)
    building         = models.CharField('건물', max_length=100, blank=True)
    floor            = models.CharField('층', max_length=20, blank=True)
    install_location = models.CharField('설치장소', max_length=200, blank=True)
    device_id        = models.CharField('장비 ID', max_length=100, blank=True)
    network_type     = models.CharField('망구분', max_length=50, blank=True, db_index=True)
    speed            = models.CharField('속도', max_length=20, blank=True)
    tier             = models.CharField('계위', max_length=20, blank=True)
    origin           = models.CharField('국산/외산', max_length=10, blank=True)
    mgmt             = models.CharField('MGMT', max_length=10, blank=True)
    install_year     = models.PositiveSmallIntegerField('도입년', null=True, blank=True)

    class Meta:
        db_table = 'school_equipment'
        verbose_name = '학교 장비'
        verbose_name_plural = '학교 장비 목록'
        indexes = [
            models.Index(fields=['school', 'category']),
            models.Index(fields=['school', 'network_type']),
        ]

    def __str__(self):
        return f'{self.school.name} - {self.category} {self.model_name} ({self.device_id})'
