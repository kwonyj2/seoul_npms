"""
incidents 앱 모델
장애접수, 인력배정, 처리, SLA 관리
"""
from django.db import models
from django.utils import timezone
from core.storage import NasMediaStorage

lazy_nas_storage = NasMediaStorage()


class IncidentCategory(models.Model):
    """장애 대분류"""
    CATEGORY_CHOICES = [
        ('wired',     '유선망'),
        ('wireless',  '무선망'),
        ('cable',     '케이블'),
        ('devut',     '디벗'),
        ('board',     '전자칠판'),
        ('office',    '사무기기'),
        ('inquiry',   '단순문의'),
        ('network_work', '네트워크 작업'),
    ]
    code  = models.CharField('코드', max_length=20, unique=True, choices=CATEGORY_CHOICES)
    name  = models.CharField('분류명', max_length=50)
    order = models.PositiveSmallIntegerField('정렬순서', default=0)
    is_active = models.BooleanField('활성', default=True)

    class Meta:
        db_table = 'incident_categories'
        verbose_name = '장애 대분류'
        verbose_name_plural = '장애 대분류 목록'
        ordering = ['order']

    def __str__(self):
        return self.name


class IncidentSubcategory(models.Model):
    """장애 소분류"""
    category   = models.ForeignKey(IncidentCategory, on_delete=models.CASCADE, verbose_name='대분류', related_name='subcategories')
    name       = models.CharField('소분류명', max_length=100)
    order      = models.PositiveSmallIntegerField('정렬순서', default=0)
    is_other   = models.BooleanField('기타항목', default=False, help_text='선택 시 내용 직접 입력')
    is_active  = models.BooleanField('활성', default=True)

    class Meta:
        db_table = 'incident_subcategories'
        verbose_name = '장애 소분류'
        verbose_name_plural = '장애 소분류 목록'
        ordering = ['category', 'order']

    def __str__(self):
        return f'{self.category.name} > {self.name}'


class Incident(models.Model):
    """장애 접수 메인 테이블"""
    STATUS_CHOICES = [
        ('received',    '접수'),
        ('assigned',    '배정'),
        ('moving',      '이동중'),
        ('arrived',     '도착'),
        ('processing',  '처리중'),
        ('completed',   '완료'),
        ('cancelled',   '취소'),
    ]
    PRIORITY_CHOICES = [
        ('critical', '긴급'),
        ('high',     '높음'),
        ('medium',   '보통'),
        ('low',      '낮음'),
    ]
    CONTACT_METHOD_CHOICES = [
        ('phone',   '전화'),
        ('visit',   '방문'),
        ('system',  '시스템'),
        ('email',   '이메일'),
        ('auto',    '자동감지'),
    ]

    # 접수번호: 접수일8자리_001 형식
    incident_number = models.CharField('장애접수번호', max_length=20, unique=True, db_index=True)
    school          = models.ForeignKey('schools.School', on_delete=models.PROTECT, verbose_name='학교', related_name='incidents')
    category        = models.ForeignKey(IncidentCategory, on_delete=models.PROTECT, verbose_name='장애 대분류')
    subcategory     = models.ForeignKey(IncidentSubcategory, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='장애 소분류')
    other_detail    = models.CharField('기타 소분류 상세', max_length=200, blank=True)

    status          = models.CharField('상태', max_length=20, choices=STATUS_CHOICES, default='received')
    priority        = models.CharField('긴급도', max_length=10, choices=PRIORITY_CHOICES, default='medium')

    # 접수 정보
    contact_method  = models.CharField('접수방법', max_length=20, choices=CONTACT_METHOD_CHOICES, default='phone')
    received_by     = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
                                        verbose_name='접수자', related_name='received_incidents')
    requester_name  = models.CharField('요청자', max_length=50)
    requester_phone = models.CharField('요청자 연락처', max_length=20)
    requester_position = models.CharField('요청자 직책', max_length=50, blank=True)
    description     = models.TextField('요청내용')

    # 시간 추적
    received_at     = models.DateTimeField('접수일시', default=timezone.now)
    assigned_at     = models.DateTimeField('배정일시', null=True, blank=True)
    arrived_at      = models.DateTimeField('도착일시', null=True, blank=True)
    started_at      = models.DateTimeField('처리시작일시', null=True, blank=True)
    completed_at    = models.DateTimeField('처리완료일시', null=True, blank=True)

    # 처리 내용
    resolution      = models.TextField('처리내용', blank=True)
    resolution_type = models.CharField('처리유형', max_length=100, blank=True)

    # SLA
    sla_arrival_ok   = models.BooleanField('SLA도착준수', null=True)
    sla_resolve_ok   = models.BooleanField('SLA처리준수', null=True)

    # SLA 협약서 — 장애 유형 (붙임3)
    FAULT_TYPE_CHOICES = [
        ('service_stop',  '서비스 중단'),
        ('service_delay', '서비스 지연'),
        ('malfunction',   '서비스 오작동'),
        ('terminal',      '단말 장애'),
        ('infra',         '기반시설 장애'),
        ('cyber',         '사이버 침해'),
        ('other',         '기타'),
    ]
    fault_type     = models.CharField('장애 유형', max_length=20,
                                      choices=FAULT_TYPE_CHOICES, default='service_stop')
    is_human_error = models.BooleanField('인적장애여부', default=False,
                                         help_text='조작미숙·무단작업·점검미흡·실수·고의 등으로 인한 장애')

    # 장애 발생 위치 (건물→층→교실 cascade)
    location_building  = models.ForeignKey(
        'schools.SchoolBuilding', on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name='장애위치(건물)'
    )
    location_floor     = models.ForeignKey(
        'schools.SchoolFloor', on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name='장애위치(층)'
    )
    location_room      = models.ForeignKey(
        'schools.SchoolRoom', on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name='장애위치(교실)'
    )
    location_detail    = models.CharField('위치 상세', max_length=200, blank=True)

    # 고객 협의 방문 약속 (SLA 기준시간 조정)
    appointment_at     = models.DateTimeField('방문 약속시간', null=True, blank=True,
                                              help_text='고객 협의로 방문 약속 시 SLA 기준이 이 시각으로 조정됨')
    customer_call_at   = models.DateTimeField('고객 통화시간', null=True, blank=True)
    customer_call_note = models.TextField('고객 통화내용', blank=True)

    # 재발 장애 연결
    is_recurrence      = models.BooleanField('재발장애여부', default=False)
    original_incident  = models.ForeignKey(
        'self', on_delete=models.SET_NULL,
        null=True, blank=True,
        verbose_name='원장애', related_name='recurrences',
    )

    # 만족도
    satisfaction_sent    = models.BooleanField('만족도조사발송', default=False)
    satisfaction_score   = models.PositiveSmallIntegerField('만족도점수', null=True, blank=True)
    satisfaction_comment = models.TextField('만족도의견', blank=True)

    # PDF 보고서
    report_pdf_path = models.CharField('보고서PDF경로', max_length=500, blank=True)

    created_at = models.DateTimeField('등록일시', auto_now_add=True)
    updated_at = models.DateTimeField('수정일시', auto_now=True)

    class Meta:
        db_table = 'incidents'
        verbose_name = '장애접수'
        verbose_name_plural = '장애접수 목록'
        ordering = ['-received_at']
        indexes = [
            models.Index(fields=['status', 'received_at']),
            models.Index(fields=['school', 'status']),
            models.Index(fields=['received_at']),
            models.Index(fields=['category', 'received_at']),
        ]

    def __str__(self):
        return f'{self.incident_number} - {self.school.name}'

    def get_elapsed_minutes(self):
        """접수 후 경과 시간(분)"""
        end = self.completed_at or timezone.now()
        return int((end - self.received_at).total_seconds() / 60)

    @classmethod
    def generate_number(cls, received_at=None):
        """장애번호 자동 생성 (YYYYMMDD_NNN)"""
        if received_at is None:
            received_at = timezone.now()
        date_str = received_at.strftime('%Y%m%d')
        today_count = cls.objects.filter(incident_number__startswith=date_str).count()
        return f'{date_str}_{str(today_count + 1).zfill(3)}'


class IncidentAssignment(models.Model):
    """장애 인력 배정"""
    incident   = models.ForeignKey(Incident, on_delete=models.CASCADE, verbose_name='장애', related_name='assignments')
    worker     = models.ForeignKey('accounts.User', on_delete=models.CASCADE, verbose_name='배정인력', related_name='incident_assignments')
    assigned_by  = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True,
                                     verbose_name='배정자', related_name='assigned_incidents')
    is_ai_assigned = models.BooleanField('AI자동배정', default=False)
    distance_km    = models.DecimalField('거리(km)', max_digits=6, decimal_places=2, null=True, blank=True)
    eta_minutes    = models.PositiveIntegerField('예상도착(분)', null=True, blank=True)

    accepted_at    = models.DateTimeField('수락일시', null=True, blank=True)
    departed_at    = models.DateTimeField('출발일시', null=True, blank=True)
    arrived_at     = models.DateTimeField('도착일시', null=True, blank=True)
    completed_at   = models.DateTimeField('완료일시', null=True, blank=True)

    is_accepted    = models.BooleanField('수락여부', null=True)
    reject_reason  = models.CharField('거부사유', max_length=200, blank=True)

    assigned_at    = models.DateTimeField('배정일시', auto_now_add=True)
    note           = models.TextField('비고', blank=True)

    class Meta:
        db_table = 'incident_assignments'
        verbose_name = '장애 인력 배정'
        verbose_name_plural = '장애 인력 배정 목록'
        ordering = ['-assigned_at']

    def __str__(self):
        return f'{self.incident.incident_number} → {self.worker.name}'


class IncidentStatusHistory(models.Model):
    """장애 상태 변경 이력"""
    incident   = models.ForeignKey(Incident, on_delete=models.CASCADE, verbose_name='장애', related_name='status_history')
    from_status= models.CharField('이전상태', max_length=20, blank=True)
    to_status  = models.CharField('변경상태', max_length=20)
    changed_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, verbose_name='변경자')
    note       = models.TextField('비고', blank=True)
    changed_at = models.DateTimeField('변경일시', auto_now_add=True)

    class Meta:
        db_table = 'incident_status_history'
        verbose_name = '장애 상태 이력'
        ordering = ['-changed_at']


class IncidentComment(models.Model):
    """장애 처리 메모/댓글"""
    incident   = models.ForeignKey(Incident, on_delete=models.CASCADE, verbose_name='장애', related_name='comments')
    author     = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, verbose_name='작성자')
    content    = models.TextField('내용')
    is_internal= models.BooleanField('내부메모', default=False)
    created_at = models.DateTimeField('작성일시', auto_now_add=True)
    updated_at = models.DateTimeField('수정일시', auto_now=True)

    class Meta:
        db_table = 'incident_comments'
        verbose_name = '장애 댓글'
        ordering = ['created_at']


def incident_photo_upload_path(instance, filename):
    """장애처리 현장사진 저장 경로 및 파일명 생성
    저장경로: 산출물/장애처리 현장사진/
    파일명 : 2026년 테크센터-장애처리 현장사진_학교명_장애접수번호[_N].jpg
    """
    import os
    ext = os.path.splitext(filename)[1].lower() or '.jpg'
    school_name = '미상'
    incident_number = 'unknown'
    if instance.incident_id:
        try:
            school_name = instance.incident.school.name
        except Exception:
            pass
        incident_number = instance.incident.incident_number
    base = f"2026년 테크센터-장애처리 현장사진_{school_name}_{incident_number}"
    existing = IncidentPhoto.objects.filter(incident_id=instance.incident_id).count()
    if existing == 0:
        fname = f"{base}{ext}"
    else:
        fname = f"{base}_{existing + 1}{ext}"
    return os.path.join('산출물', '장애처리 현장사진', fname)


class IncidentPhoto(models.Model):
    """장애 첨부 사진"""
    PHOTO_TYPE_CHOICES = [
        ('before', '처리 전'),
        ('after',  '처리 후'),
        ('etc',    '기타'),
    ]
    incident    = models.ForeignKey(Incident, on_delete=models.CASCADE, verbose_name='장애', related_name='photos')
    photo_type  = models.CharField('사진유형', max_length=10, choices=PHOTO_TYPE_CHOICES, default='etc')
    image       = models.ImageField('이미지', upload_to=incident_photo_upload_path,
                                        storage=lazy_nas_storage)
    caption     = models.CharField('설명', max_length=200, blank=True)
    gps_lat     = models.DecimalField('위도', max_digits=10, decimal_places=7, null=True, blank=True)
    gps_lng     = models.DecimalField('경도', max_digits=10, decimal_places=7, null=True, blank=True)
    uploaded_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, verbose_name='업로더')
    uploaded_at = models.DateTimeField('업로드일시', auto_now_add=True)

    class Meta:
        db_table = 'incident_photos'
        verbose_name = '장애 사진'

    def __str__(self):
        return f'{self.incident.incident_number} - {self.get_photo_type_display()}'


class IncidentSLA(models.Model):
    """장애 SLA 측정 결과"""
    incident       = models.OneToOneField(Incident, on_delete=models.CASCADE, verbose_name='장애', related_name='sla')
    arrival_target = models.DateTimeField('도착 목표시각')
    resolve_target = models.DateTimeField('처리 목표시각')
    arrival_actual = models.DateTimeField('실제 도착시각', null=True, blank=True)
    resolve_actual = models.DateTimeField('실제 완료시각', null=True, blank=True)
    arrival_ok     = models.BooleanField('도착 SLA 준수', null=True)
    resolve_ok     = models.BooleanField('처리 SLA 준수', null=True)
    arrival_diff_min = models.IntegerField('도착 차이(분)', null=True, blank=True)
    resolve_diff_min = models.IntegerField('처리 차이(분)', null=True, blank=True)
    is_adjusted    = models.BooleanField('고객협의 조정', default=False,
                                          help_text='고객 협의에 의해 SLA 기준시간이 조정된 경우')
    created_at     = models.DateTimeField('생성일시', auto_now_add=True)
    updated_at     = models.DateTimeField('수정일시', auto_now=True)

    class Meta:
        db_table = 'incident_sla'
        verbose_name = '장애 SLA'


class SLARule(models.Model):
    """SLA 기준 설정"""
    name              = models.CharField('규칙명', max_length=100, default='기본 SLA')
    arrival_hours     = models.PositiveSmallIntegerField('도착 기준(시간)', default=2)
    resolve_hours     = models.PositiveSmallIntegerField('처리 기준(시간)', default=8)
    is_active         = models.BooleanField('적용중', default=True)
    apply_from        = models.DateField('적용시작일')
    apply_to          = models.DateField('적용종료일', null=True, blank=True)
    created_by        = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, verbose_name='등록자')
    created_at        = models.DateTimeField('등록일시', auto_now_add=True)

    class Meta:
        db_table = 'sla_rules'
        verbose_name = 'SLA 기준'

    def __str__(self):
        return f'{self.name} (도착:{self.arrival_hours}h, 처리:{self.resolve_hours}h)'


class SLAMonthly(models.Model):
    """
    월간 SLA 종합 측정 결과 (협약서 붙임1 기준)
    매월 9개 지표 측정값·점수·가중치 환산점수 저장
    """
    GRADE_CHOICES = [
        ('excellent', '탁월'),
        ('good',      '우수'),
        ('normal',    '보통'),
        ('poor',      '미흡'),
        ('bad',       '불량'),
    ]

    year  = models.PositiveSmallIntegerField('연도')
    month = models.PositiveSmallIntegerField('월')

    # ── 운영관리 ──────────────────────────────
    # 1. 장비 가동률 (가중치 20%)
    uptime_pct       = models.FloatField('장비 가동률(%)', null=True, blank=True)
    uptime_score     = models.FloatField('장비 가동률 점수', null=True, blank=True)
    uptime_total_min = models.IntegerField('월 가동시간(분)', null=True, blank=True)
    uptime_fault_min = models.IntegerField('서비스중단시간(분)', null=True, blank=True)
    uptime_maint_min = models.IntegerField('계획작업시간(분)', null=True, blank=True)

    # 2. 예방점검 준수율 (가중치 10%)
    inspection_pct        = models.FloatField('예방점검 준수율(%)', null=True, blank=True)
    inspection_score      = models.FloatField('예방점검 준수율 점수', null=True, blank=True)
    inspection_total      = models.IntegerField('전체 예방점검 건수', null=True, blank=True)
    inspection_completed  = models.IntegerField('완료 예방점검 건수', null=True, blank=True)

    # ── 장애관리 ──────────────────────────────
    # 3. 평균 장애시간 (가중치 10%)
    avg_fault_min    = models.FloatField('평균 장애시간(분)', null=True, blank=True)
    avg_fault_score  = models.FloatField('평균 장애시간 점수', null=True, blank=True)

    # 4. 장애건수 (가중치 10%)
    fault_count      = models.IntegerField('장애건수', null=True, blank=True)
    fault_count_score = models.FloatField('장애건수 점수', null=True, blank=True)

    # 5. 장애조치 최대 허용시간 초과 건수 (가중치 10%)
    overtime_count   = models.IntegerField('초과 건수', null=True, blank=True)
    overtime_score   = models.FloatField('초과 건수 점수', null=True, blank=True)

    # 6. 인적장애 건수 (가중치 10%)
    human_error_count  = models.IntegerField('인적장애 건수', null=True, blank=True)
    human_error_score  = models.FloatField('인적장애 점수', null=True, blank=True)

    # 7. 반복장애 건수 (가중치 10%)
    recurrence_count  = models.IntegerField('반복장애 건수', null=True, blank=True)
    recurrence_score  = models.FloatField('반복장애 점수', null=True, blank=True)

    # ── 정보보안관리 ───────────────────────────
    # 8. 보안위규 건수 (가중치 10%) — 수동 입력
    security_count   = models.IntegerField('보안위규 건수', default=0)
    security_score   = models.FloatField('보안위규 점수', null=True, blank=True)
    security_note    = models.TextField('보안위규 내용', blank=True)

    # ── 서비스지원 ──────────────────────────────
    # 9. 서비스 만족도 (가중치 10%)
    satisfaction_pct   = models.FloatField('서비스 만족도(%)', null=True, blank=True)
    satisfaction_score = models.FloatField('서비스 만족도 점수', null=True, blank=True)
    satisfaction_count = models.IntegerField('만족도 응답 건수', null=True, blank=True)

    # ── 종합 결과 ──────────────────────────────
    total_score = models.FloatField('종합점수', null=True, blank=True)
    grade       = models.CharField('평가등급', max_length=20, choices=GRADE_CHOICES, blank=True)
    memo        = models.TextField('비고', blank=True)

    calculated_at = models.DateTimeField('산출일시', null=True, blank=True)
    created_by    = models.ForeignKey('accounts.User', on_delete=models.SET_NULL,
                                      null=True, blank=True, verbose_name='산출자')
    created_at    = models.DateTimeField('등록일시', auto_now_add=True)
    updated_at    = models.DateTimeField('수정일시', auto_now=True)

    class Meta:
        db_table        = 'sla_monthly'
        verbose_name    = 'SLA 월간 측정'
        unique_together = [['year', 'month']]
        ordering        = ['-year', '-month']

    def __str__(self):
        return f'{self.year}년 {self.month}월 SLA ({self.grade or "미산출"})'


class WorkOrder(models.Model):
    """
    작업지시서 — 장애 접수에서 자동 생성
    장애 배정 시 자동 생성, 현장 기사가 수행 내용 기록
    """
    STATUS_CHOICES = [
        ('issued',      '발행'),
        ('in_progress', '수행중'),
        ('completed',   '완료'),
        ('confirmed',   '확인완료'),
        ('cancelled',   '취소'),
    ]
    WORK_TYPE_CHOICES = [
        ('repair',      '수리/복구'),
        ('installation','설치'),
        ('inspection',  '점검'),
        ('replacement', '교체'),
        ('config',      '설정변경'),
        ('other',       '기타'),
    ]

    incident       = models.ForeignKey(
        Incident, on_delete=models.CASCADE,
        related_name='work_orders', verbose_name='연계 장애'
    )
    work_order_number = models.CharField('작업지시번호', max_length=20, unique=True, db_index=True)
    school         = models.ForeignKey(
        'schools.School', on_delete=models.PROTECT,
        related_name='work_orders', verbose_name='학교'
    )
    assigned_to    = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='work_orders', verbose_name='담당자'
    )
    created_by     = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_work_orders', verbose_name='작성자'
    )
    status         = models.CharField('상태', max_length=20, choices=STATUS_CHOICES, default='issued')
    work_type      = models.CharField('작업유형', max_length=20, choices=WORK_TYPE_CHOICES, default='repair')
    title          = models.CharField('작업제목', max_length=200)
    work_description = models.TextField('작업지시 내용')
    required_parts   = models.TextField('필요 자재', blank=True)

    # 수행 결과
    actual_work    = models.TextField('실제 수행 내용', blank=True)
    parts_used     = models.TextField('사용 자재', blank=True)
    work_note      = models.TextField('특이사항', blank=True)

    # 일정
    due_date       = models.DateField('완료기한', null=True, blank=True)
    started_at     = models.DateTimeField('수행시작', null=True, blank=True)
    completed_at   = models.DateTimeField('수행완료', null=True, blank=True)
    confirmed_at   = models.DateTimeField('확인완료', null=True, blank=True)
    confirmed_by   = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='confirmed_work_orders', verbose_name='확인자'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table     = 'work_orders'
        verbose_name = '작업지시서'
        ordering     = ['-created_at']

    def __str__(self):
        return f'{self.work_order_number} - {self.title}'

    @classmethod
    def generate_number(cls, created_at=None):
        """작업지시번호 자동 생성 (WO-YYYYMMDD-NNN)"""
        if created_at is None:
            created_at = timezone.now()
        date_str = created_at.strftime('%Y%m%d')
        today_count = cls.objects.filter(work_order_number__contains=date_str).count()
        return f'WO-{date_str}-{str(today_count + 1).zfill(3)}'
