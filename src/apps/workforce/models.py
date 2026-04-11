"""
workforce 앱 모델
인력 스케줄, 업무 배정, 근태 관리
"""
from django.db import models
from django.utils import timezone


class WorkScheduleType(models.Model):
    """업무 유형"""
    TYPE_CHOICES = [
        ('regular_check',  '정기점검'),
        ('incident',       '장애처리'),
        ('cable',          '케이블설치'),
        ('edu_request',    '교육지원청 요구업무'),
        ('special_check',  '특별점검'),
        ('switch_install', '스위치설치'),
        ('other',          '기타'),
    ]
    code      = models.CharField('코드', max_length=30, unique=True, choices=TYPE_CHOICES)
    name      = models.CharField('업무유형명', max_length=50)
    color     = models.CharField('캘린더 색상', max_length=7, default='#3788d8')
    order     = models.PositiveSmallIntegerField('정렬순서', default=0)
    is_active = models.BooleanField('활성', default=True)

    class Meta:
        db_table = 'work_schedule_types'
        verbose_name = '업무 유형'
        verbose_name_plural = '업무 유형 목록'
        ordering = ['order']

    def __str__(self):
        return self.name


class WorkSchedule(models.Model):
    """인력 업무 일정"""
    STATUS_CHOICES = [
        ('planned',    '예정'),
        ('in_progress','진행중'),
        ('completed',  '완료'),
        ('cancelled',  '취소'),
    ]
    worker       = models.ForeignKey('accounts.User', on_delete=models.CASCADE, verbose_name='인력', related_name='schedules')
    schedule_type= models.ForeignKey(WorkScheduleType, on_delete=models.PROTECT, verbose_name='업무유형')
    school       = models.ForeignKey('schools.School', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='방문학교')
    incident     = models.ForeignKey('incidents.Incident', on_delete=models.SET_NULL, null=True, blank=True,
                                     verbose_name='연관장애', related_name='schedules')
    title        = models.CharField('일정제목', max_length=200)
    description  = models.TextField('상세내용', blank=True)
    start_dt     = models.DateTimeField('시작일시')
    end_dt       = models.DateTimeField('종료일시')
    status       = models.CharField('상태', max_length=20, choices=STATUS_CHOICES, default='planned')
    created_by   = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True,
                                     verbose_name='등록자', related_name='created_schedules')
    created_at   = models.DateTimeField('등록일시', auto_now_add=True)
    updated_at   = models.DateTimeField('수정일시', auto_now=True)

    class Meta:
        db_table = 'work_schedules'
        verbose_name = '업무 일정'
        verbose_name_plural = '업무 일정 목록'
        ordering = ['start_dt']
        indexes = [
            models.Index(fields=['worker', 'start_dt']),
            models.Index(fields=['school', 'start_dt']),
        ]

    def __str__(self):
        return f'{self.worker.name} - {self.title} ({self.start_dt.strftime("%Y-%m-%d")})'


class AttendanceLog(models.Model):
    """근태 기록"""
    STATUS_CHOICES = [
        ('normal',      '정상'),
        ('late',        '지각'),
        ('absent',      '결근'),
        ('early',       '조퇴'),
        ('leave',       '연차'),
        ('business',    '출장'),
        ('sick_leave',  '병가'),
        ('vacation',    '휴가'),
        ('half_leave',  '반차'),
        ('resignation', '퇴직'),
        ('other',       '기타'),
    ]
    worker       = models.ForeignKey('accounts.User', on_delete=models.CASCADE, verbose_name='인력', related_name='attendance_logs')
    work_date    = models.DateField('근무일')
    check_in_at  = models.DateTimeField('출근시각', null=True, blank=True)
    check_out_at = models.DateTimeField('퇴근시각', null=True, blank=True)
    check_in_lat = models.DecimalField('출근위도', max_digits=10, decimal_places=7, null=True, blank=True)
    check_in_lng = models.DecimalField('출근경도', max_digits=10, decimal_places=7, null=True, blank=True)
    check_out_lat= models.DecimalField('퇴근위도', max_digits=10, decimal_places=7, null=True, blank=True)
    check_out_lng= models.DecimalField('퇴근경도', max_digits=10, decimal_places=7, null=True, blank=True)
    status           = models.CharField('근태상태', max_length=20, choices=STATUS_CHOICES, default='normal')
    note             = models.TextField('비고', blank=True)
    check_in_device  = models.CharField('출근단말', max_length=10, choices=[('pc','PC'),('mobile','모바일'),('unknown','알수없음')], blank=True)
    check_out_device = models.CharField('퇴근단말', max_length=10, choices=[('pc','PC'),('mobile','모바일'),('unknown','알수없음')], blank=True)
    created_at       = models.DateTimeField('등록일시', auto_now_add=True)

    class Meta:
        db_table = 'attendance_logs'
        verbose_name = '근태 기록'
        verbose_name_plural = '근태 기록 목록'
        unique_together = [['worker', 'work_date']]
        ordering = ['-work_date']

    def __str__(self):
        return f'{self.worker.name} - {self.work_date}'

    def get_work_hours(self):
        """실근무시간(시간)"""
        if self.check_in_at and self.check_out_at:
            return round((self.check_out_at - self.check_in_at).total_seconds() / 3600, 1)
        return None


class AttendanceException(models.Model):
    """근태 이상 알림 - 근무시간 내 이탈, 자택 위치 등"""
    ALERT_TYPE_CHOICES = [
        ('home_location',  '근무시간 내 자택 위치'),
        ('out_of_area',    '담당구역 이탈'),
        ('no_checkin',     '미출근'),
        ('long_stationary','장시간 미이동'),
    ]
    worker     = models.ForeignKey('accounts.User', on_delete=models.CASCADE, verbose_name='인력')
    alert_type = models.CharField('알림유형', max_length=30, choices=ALERT_TYPE_CHOICES)
    detected_at= models.DateTimeField('감지일시', auto_now_add=True)
    lat        = models.DecimalField('위도', max_digits=10, decimal_places=7, null=True, blank=True)
    lng        = models.DecimalField('경도', max_digits=10, decimal_places=7, null=True, blank=True)
    is_confirmed = models.BooleanField('확인여부', default=False)
    confirmed_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name='confirmed_exceptions', verbose_name='확인자')
    note       = models.TextField('비고', blank=True)

    class Meta:
        db_table = 'attendance_exceptions'
        verbose_name = '근태 이상 알림'
        verbose_name_plural = '근태 이상 알림 목록'
        ordering = ['-detected_at']


class WorkerProfile(models.Model):
    """현장기사 추가 프로필 (신상·경력)"""
    worker        = models.OneToOneField(
        'accounts.User', on_delete=models.CASCADE,
        related_name='worker_profile', verbose_name='인력'
    )
    birth_date    = models.DateField('생년월일', null=True, blank=True)
    join_date     = models.DateField('입사일',   null=True, blank=True)
    career_summary= models.TextField('경력요약', blank=True)
    bio           = models.TextField('소개',     blank=True)
    notes         = models.TextField('비고',     blank=True)
    updated_at    = models.DateTimeField('수정일시', auto_now=True)

    class Meta:
        db_table     = 'worker_profiles'
        verbose_name = '인력 프로필'
        verbose_name_plural = '인력 프로필 목록'

    def __str__(self):
        return f'{self.worker.name} 프로필'


class TaskAssignment(models.Model):
    """작업 배정 (스케줄 내 세부 작업)"""
    STATUS_CHOICES = [
        ('pending',   '대기'),
        ('started',   '시작'),
        ('done',      '완료'),
        ('skipped',   '건너뜀'),
    ]
    schedule    = models.ForeignKey(WorkSchedule, on_delete=models.CASCADE, verbose_name='일정', related_name='tasks')
    school      = models.ForeignKey('schools.School', on_delete=models.PROTECT, verbose_name='학교')
    description = models.TextField('작업내용')
    status      = models.CharField('상태', max_length=20, choices=STATUS_CHOICES, default='pending')
    started_at  = models.DateTimeField('시작일시', null=True, blank=True)
    done_at     = models.DateTimeField('완료일시', null=True, blank=True)
    note        = models.TextField('비고', blank=True)
    order       = models.PositiveSmallIntegerField('순서', default=0)

    class Meta:
        db_table = 'task_assignments'
        verbose_name = '작업 배정'
        ordering = ['schedule', 'order']
