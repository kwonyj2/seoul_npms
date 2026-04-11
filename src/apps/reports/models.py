"""
reports 앱 모델
보고서 템플릿, 버전 관리, 전자서명
"""
from django.db import models


class ReportTemplate(models.Model):
    TYPE_CHOICES = [
        ('incident',      '장애처리 확인서'),
        ('regular',       '정기점검'),
        ('cable',         '소규모 네트워크 포설'),
        ('switch_install','스위치 설치 확인서'),
        ('quarterly',     '분기별 점검'),
        ('other',         '기타'),
    ]
    code          = models.CharField('코드', max_length=30, unique=True)
    name          = models.CharField('템플릿명', max_length=100)
    report_type   = models.CharField('보고서유형', max_length=20, choices=TYPE_CHOICES)
    template_html = models.TextField('HTML 템플릿')
    fields_schema = models.JSONField('필드 정의', default=dict)
    is_active     = models.BooleanField('활성', default=True)
    created_by    = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, verbose_name='등록자')
    created_at    = models.DateTimeField('등록일시', auto_now_add=True)

    class Meta:
        db_table = 'report_templates'
        verbose_name = '보고서 템플릿'

    def __str__(self):
        return self.name


class Report(models.Model):
    STATUS_CHOICES = [
        ('draft',     '작성중'),
        ('completed', '완료'),
        ('archived',  '보관'),
    ]
    template     = models.ForeignKey(ReportTemplate, on_delete=models.PROTECT, verbose_name='템플릿')
    school       = models.ForeignKey('schools.School', on_delete=models.CASCADE, verbose_name='학교', related_name='reports')
    incident     = models.ForeignKey('incidents.Incident', on_delete=models.SET_NULL, null=True, blank=True,
                                     verbose_name='관련장애', related_name='reports')
    title        = models.CharField('보고서제목', max_length=200)
    status       = models.CharField('상태', max_length=10, choices=STATUS_CHOICES, default='draft')
    data         = models.JSONField('보고서 데이터', default=dict)
    pdf_path     = models.CharField('PDF경로', max_length=500, blank=True)
    is_final     = models.BooleanField('최종확정', default=False)
    created_by   = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, verbose_name='작성자')
    completed_at = models.DateTimeField('완료일시', null=True, blank=True)
    created_at   = models.DateTimeField('작성일시', auto_now_add=True)
    updated_at   = models.DateTimeField('수정일시', auto_now=True)

    class Meta:
        db_table = 'reports'
        verbose_name = '보고서'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.school.name} - {self.title}'


class ReportVersion(models.Model):
    report   = models.ForeignKey(Report, on_delete=models.CASCADE, verbose_name='보고서', related_name='versions')
    version  = models.PositiveSmallIntegerField('버전')
    data     = models.JSONField('스냅샷', default=dict)
    saved_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, verbose_name='저장자')
    saved_at = models.DateTimeField('저장일시', auto_now_add=True)
    note     = models.CharField('버전메모', max_length=200, blank=True)

    class Meta:
        db_table = 'report_versions'
        verbose_name = '보고서 버전'
        unique_together = [['report', 'version']]
        ordering = ['-version']


class ReportSignature(models.Model):
    report         = models.ForeignKey(Report, on_delete=models.CASCADE, verbose_name='보고서', related_name='signatures')
    signer         = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, verbose_name='서명자')
    signer_name    = models.CharField('서명자명', max_length=50)
    role           = models.CharField('역할', max_length=50, blank=True)
    signature_data = models.TextField('서명 데이터(Base64)')
    signed_at      = models.DateTimeField('서명일시', auto_now_add=True)
    is_valid       = models.BooleanField('유효', default=True)

    class Meta:
        db_table = 'report_signatures'
        verbose_name = '전자서명'
