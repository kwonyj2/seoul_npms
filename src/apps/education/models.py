"""
교육관리 앱 모델
교육 카테고리 → 교육 과정 → 콘텐츠(동영상/자료) → 수강 이력 → 이수증
"""
from django.db import models
from django.utils import timezone


class EducationCategory(models.Model):
    """교육 분류 (보안교육, 안전교육, 네트워크교육 등)"""
    ICON_CHOICES = [
        ('bi-shield-lock',    '보안'),
        ('bi-cone-striped',   '안전'),
        ('bi-hdd-network',    '네트워크'),
        ('bi-mortarboard',    '직무'),
        ('bi-book',           '일반'),
    ]
    COLOR_CHOICES = [
        ('danger',   '빨강'),
        ('warning',  '노랑'),
        ('primary',  '파랑'),
        ('success',  '초록'),
        ('info',     '하늘'),
        ('secondary','회색'),
    ]
    name   = models.CharField('분류명', max_length=50)
    icon   = models.CharField('아이콘', max_length=50, default='bi-book')
    color  = models.CharField('색상', max_length=20, default='primary')
    order  = models.PositiveSmallIntegerField('정렬 순서', default=0)
    is_active = models.BooleanField('활성', default=True)

    class Meta:
        db_table = 'education_categories'
        ordering = ['order', 'id']
        verbose_name = '교육 분류'
        verbose_name_plural = '교육 분류 목록'

    def __str__(self):
        return self.name


class EducationCourse(models.Model):
    """교육 과정"""
    category        = models.ForeignKey(EducationCategory, on_delete=models.CASCADE,
                                        related_name='courses', verbose_name='분류')
    title           = models.CharField('교육명', max_length=200)
    description     = models.TextField('교육 설명', blank=True)
    instructor      = models.CharField('강사/출처', max_length=100, blank=True)
    duration_minutes = models.PositiveIntegerField('교육 시간(분)', default=0)
    pass_percent    = models.PositiveSmallIntegerField('이수 기준(%)', default=80,
                                                        help_text='동영상 시청률 기준')
    is_required     = models.BooleanField('필수 교육', default=False)
    is_active       = models.BooleanField('활성', default=True)
    created_by      = models.ForeignKey('accounts.User', on_delete=models.SET_NULL,
                                         null=True, blank=True, verbose_name='등록자')
    created_at      = models.DateTimeField('등록일시', auto_now_add=True)
    updated_at      = models.DateTimeField('수정일시', auto_now=True)

    class Meta:
        db_table = 'education_courses'
        ordering = ['-created_at']
        verbose_name = '교육 과정'
        verbose_name_plural = '교육 과정 목록'

    def __str__(self):
        return self.title

    def completion_count(self):
        return self.completions.count()


class EducationContent(models.Model):
    """교육 콘텐츠 (동영상 또는 자료 파일)"""
    TYPE_VIDEO    = 'video'
    TYPE_DOCUMENT = 'document'
    TYPE_LINK     = 'link'
    TYPE_CHOICES  = [
        (TYPE_VIDEO,    '동영상'),
        (TYPE_DOCUMENT, '자료'),
        (TYPE_LINK,     '외부링크'),
    ]

    course       = models.ForeignKey(EducationCourse, on_delete=models.CASCADE,
                                     related_name='contents', verbose_name='교육 과정')
    title        = models.CharField('제목', max_length=200)
    content_type = models.CharField('유형', max_length=20, choices=TYPE_CHOICES, default=TYPE_VIDEO)
    file         = models.FileField('파일', upload_to='education/', null=True, blank=True)
    external_url = models.URLField('외부 URL', blank=True)
    duration_seconds = models.PositiveIntegerField('영상 길이(초)', default=0)
    order        = models.PositiveSmallIntegerField('순서', default=0)
    created_at   = models.DateTimeField('등록일시', auto_now_add=True)

    class Meta:
        db_table = 'education_contents'
        ordering = ['order', 'id']
        verbose_name = '교육 콘텐츠'
        verbose_name_plural = '교육 콘텐츠 목록'

    def __str__(self):
        return f'[{self.get_content_type_display()}] {self.title}'

    @property
    def file_url(self):
        if self.file:
            return self.file.url
        return self.external_url or ''


class EducationProgress(models.Model):
    """수강 진도 (동영상 시청 진행률 추적)"""
    user         = models.ForeignKey('accounts.User', on_delete=models.CASCADE,
                                     related_name='edu_progress', verbose_name='수강자')
    content      = models.ForeignKey(EducationContent, on_delete=models.CASCADE,
                                     related_name='progress', verbose_name='콘텐츠')
    watch_seconds = models.PositiveIntegerField('시청 초', default=0)
    watch_percent = models.PositiveSmallIntegerField('시청률(%)', default=0)
    last_position = models.PositiveIntegerField('마지막 위치(초)', default=0)
    updated_at    = models.DateTimeField('갱신일시', auto_now=True)

    class Meta:
        db_table = 'education_progress'
        unique_together = ('user', 'content')
        verbose_name = '수강 진도'
        verbose_name_plural = '수강 진도 목록'


class EducationCompletion(models.Model):
    """교육 이수 기록"""
    user         = models.ForeignKey('accounts.User', on_delete=models.CASCADE,
                                     related_name='edu_completions', verbose_name='이수자')
    course       = models.ForeignKey(EducationCourse, on_delete=models.CASCADE,
                                     related_name='completions', verbose_name='교육 과정')
    completed_at = models.DateTimeField('이수일시', default=timezone.now)
    certificate_no = models.CharField('이수증 번호', max_length=30, unique=True)
    score        = models.PositiveSmallIntegerField('이수 점수(%)', default=100)

    class Meta:
        db_table = 'education_completions'
        unique_together = ('user', 'course')
        ordering = ['-completed_at']
        verbose_name = '교육 이수'
        verbose_name_plural = '교육 이수 목록'

    def __str__(self):
        return f'{self.certificate_no} — {self.user.name} / {self.course.title}'

    def save(self, *args, **kwargs):
        if not self.certificate_no:
            from django.utils import timezone as tz
            today = tz.localdate().strftime('%Y%m%d')
            last = EducationCompletion.objects.filter(
                certificate_no__startswith=f'CERT-{today}-'
            ).order_by('-certificate_no').first()
            seq = 1
            if last:
                try:
                    seq = int(last.certificate_no.split('-')[-1]) + 1
                except ValueError:
                    seq = 1
            self.certificate_no = f'CERT-{today}-{seq:03d}'
        super().save(*args, **kwargs)
