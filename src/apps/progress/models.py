"""
progress 앱 모델
정기점검 / 특별점검 / 사업점검 / 실태조사 / 사후점검 진척관리
"""
from django.db import models
from django.db.models import Count, Q


# ──────────────────────────────────────────────────
# 휴일 관리
# ──────────────────────────────────────────────────
class Holiday(models.Model):
    TYPE_CHOICES = [
        ('legal',      '법정공휴일'),
        ('custom',     '기관지정휴일'),
        ('substitute', '대체공휴일'),
    ]
    name          = models.CharField('휴일명', max_length=100)
    holiday_type  = models.CharField('유형', max_length=20, choices=TYPE_CHOICES, default='legal')
    # 매년 반복 휴일: month + day 사용, specific_date = null
    month         = models.PositiveSmallIntegerField('월', null=True, blank=True)
    day           = models.PositiveSmallIntegerField('일', null=True, blank=True)
    # 특정 연도만 적용 (대체공휴일, 설·추석 등): specific_date 사용
    specific_date = models.DateField('특정날짜', null=True, blank=True)
    is_recurring  = models.BooleanField('매년반복', default=True,
                                        help_text='True=매년 month/day 기준, False=specific_date만')
    is_active     = models.BooleanField('활성', default=True)
    note          = models.CharField('비고', max_length=200, blank=True)
    created_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table   = 'holidays'
        verbose_name = '휴일'
        ordering   = ['month', 'day']

    def __str__(self):
        if self.is_recurring:
            return f'{self.month}/{self.day} {self.name}'
        return f'{self.specific_date} {self.name}'


# ──────────────────────────────────────────────────
# 인력-지원청 담당 구역 매핑
# ──────────────────────────────────────────────────
class WorkerArea(models.Model):
    worker         = models.ForeignKey(
        'accounts.User', on_delete=models.CASCADE,
        related_name='worker_areas', verbose_name='인력'
    )
    support_center = models.ForeignKey(
        'schools.SupportCenter', on_delete=models.CASCADE,
        related_name='worker_areas', verbose_name='담당지원청'
    )
    is_primary     = models.BooleanField('주담당', default=True,
                                         help_text='False = 보조 담당 (주담당 부재 시 대리)')
    created_at     = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table        = 'worker_areas'
        verbose_name    = '인력 담당구역'
        unique_together = [['worker', 'support_center']]

    def __str__(self):
        return f'{self.worker.name} → {self.support_center.name}'


# ──────────────────────────────────────────────────
# 점검 계획
# ──────────────────────────────────────────────────
class InspectionPlan(models.Model):
    TYPE_CHOICES = [
        ('regular',   '정기점검'),
        ('special',   '특별점검'),
        ('quarterly', '분기점검'),
        ('project',   '사업점검'),
        ('survey',    '실태조사'),
        ('followup',  '사후점검'),
    ]
    STATUS_CHOICES = [
        ('draft',     '준비중'),
        ('active',    '진행중'),
        ('completed', '완료'),
    ]
    name         = models.CharField('계획명', max_length=200)
    plan_type    = models.CharField('유형', max_length=20, choices=TYPE_CHOICES, default='regular')
    year         = models.PositiveSmallIntegerField('연도')
    quarter      = models.PositiveSmallIntegerField('차수', null=True, blank=True,
        help_text='정기점검 차수 (1차/2차/3차)')
    start_date   = models.DateField('시작일')
    end_date     = models.DateField('종료일')
    description  = models.TextField('설명', blank=True)
    status       = models.CharField('상태', max_length=20, choices=STATUS_CHOICES, default='draft')
    created_by   = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True,
        related_name='created_plans', verbose_name='생성자'
    )
    created_at   = models.DateTimeField('생성일시', auto_now_add=True)
    updated_at   = models.DateTimeField('수정일시', auto_now=True)

    class Meta:
        db_table   = 'inspection_plans'
        verbose_name = '점검계획'
        ordering   = ['-year', '-start_date']

    def __str__(self):
        return f'{self.name} ({self.year})'

    @property
    def total(self):
        return self.school_inspections.count()

    @property
    def completed_count(self):
        return self.school_inspections.filter(status='completed').count()

    @property
    def progress_pct(self):
        t = self.total
        return round(self.completed_count / t * 100) if t else 0


# ──────────────────────────────────────────────────
# 학교별 점검 항목
# ──────────────────────────────────────────────────
class SchoolInspection(models.Model):
    STATUS_CHOICES = [
        ('pending',   '미정'),
        ('scheduled', '예정'),
        ('completed', '완료'),
        ('skipped',   '제외'),
    ]
    PRIORITY_CHOICES = [
        ('high',   '높음'),
        ('normal', '보통'),
        ('low',    '낮음'),
    ]

    plan            = models.ForeignKey(InspectionPlan, on_delete=models.CASCADE,
                                        related_name='school_inspections', verbose_name='계획')
    school          = models.ForeignKey('schools.School', on_delete=models.CASCADE,
                                        related_name='inspections', verbose_name='학교')
    assigned_worker = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='assigned_inspections', verbose_name='담당기사'
    )
    status          = models.CharField('상태', max_length=20, choices=STATUS_CHOICES, default='pending')
    priority        = models.CharField('우선순위', max_length=10, choices=PRIORITY_CHOICES, default='normal')
    task_type       = models.CharField('작업유형', max_length=100, blank=True,
                                       help_text='예: 스위치교체, 망구성도 현행화, AP설치')
    scheduled_date  = models.DateField('예정일', null=True, blank=True)
    completed_date  = models.DateField('완료일', null=True, blank=True)
    # 인력 업무일정 연동
    work_schedule   = models.ForeignKey(
        'workforce.WorkSchedule', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='school_inspections', verbose_name='연동업무일정'
    )
    # 인력 교체 이력
    replaced_from   = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='replaced_inspections', verbose_name='교체전기사'
    )
    replaced_at     = models.DateTimeField('교체일시', null=True, blank=True)
    report          = models.ForeignKey(
        'reports.Report', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='inspections', verbose_name='연결보고서'
    )
    notes           = models.TextField('비고', blank=True)
    created_at      = models.DateTimeField(auto_now_add=True)
    updated_at      = models.DateTimeField(auto_now=True)

    class Meta:
        db_table        = 'school_inspections'
        verbose_name    = '학교별 점검'
        unique_together = [['plan', 'school']]
        ordering        = ['scheduled_date', 'school__name']

    def __str__(self):
        return f'{self.plan.name} - {self.school.name} ({self.get_status_display()})'


# ──────────────────────────────────────────────────
# 학교 일괄 업로드 이력
# ──────────────────────────────────────────────────
class InspectionUploadLog(models.Model):
    plan          = models.ForeignKey(InspectionPlan, on_delete=models.CASCADE,
                                      related_name='upload_logs', verbose_name='점검계획')
    uploaded_by   = models.ForeignKey('accounts.User', on_delete=models.SET_NULL,
                                      null=True, verbose_name='업로드자')
    file_name     = models.CharField('파일명', max_length=255)
    total_rows    = models.PositiveIntegerField('전체행수', default=0)
    matched_count = models.PositiveIntegerField('매칭성공', default=0)
    failed_count  = models.PositiveIntegerField('매칭실패', default=0)
    added_count   = models.PositiveIntegerField('신규등록', default=0)
    result_json   = models.JSONField('결과상세', default=dict)
    uploaded_at   = models.DateTimeField('업로드일시', auto_now_add=True)

    class Meta:
        db_table   = 'inspection_upload_logs'
        verbose_name = '업로드이력'
        ordering   = ['-uploaded_at']

    def __str__(self):
        return f'{self.plan.name} 업로드 ({self.uploaded_at:%Y-%m-%d})'
