"""
audit 앱 모델
2026년 학교 디지털 인프라 통합관리(테크센터) 운영 사업 감리 대응 시스템
감리법인: (주)한국정보화기술원
감리단계: 착수 / 중간 / 종료
"""
from django.db import models
import os


def artifact_file_upload_path(instance, filename):
    """산출물 파일을 코드별 하위 폴더에 저장: 2026감리산출물/{코드}/{파일명}"""
    code = instance.template.code if instance.template else 'misc'
    return f'2026감리산출물/{code}/{filename}'


# ──────────────────────────────────────────────────
# 감리 프로젝트
# ──────────────────────────────────────────────────
class AuditProject(models.Model):
    name        = models.CharField('프로젝트명', max_length=300)
    year        = models.PositiveSmallIntegerField('연도')
    audit_firm  = models.CharField('감리법인', max_length=200, default='(주)한국정보화기술원')
    contractor  = models.CharField('사업자', max_length=200, blank=True)
    start_date  = models.DateField('사업시작일', null=True, blank=True)
    end_date    = models.DateField('사업종료일', null=True, blank=True)
    description = models.TextField('설명', blank=True)
    is_active   = models.BooleanField('활성', default=True)
    is_awarded  = models.BooleanField('낙찰/수주 완료', default=False,
                                      help_text='수주 확정 후 True로 변경하면 추가제안·기술협상 항목 등록 가능')
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        db_table     = 'audit_projects'
        verbose_name = '감리프로젝트'
        ordering     = ['-year']

    def __str__(self):
        return f'{self.name} ({self.year})'


# ──────────────────────────────────────────────────
# 요구사항 (RTM)
# ──────────────────────────────────────────────────
class Requirement(models.Model):
    CATEGORY_CHOICES = [
        ('IMR', '통합관리(IMR)'),
        ('OHR', '운영인력(OHR)'),
        ('SER', '보안(SER)'),
        ('QUR', '품질(QUR)'),
        ('COR', '제약(COR)'),
        ('PMR', '프로젝트관리(PMR)'),
        ('PSR', '프로젝트지원(PSR)'),
        ('ADD', '추가제안(ADD)'),
    ]
    STATUS_CHOICES = [
        ('not_started', '미착수'),
        ('in_progress', '진행중'),
        ('completed',   '완료'),
        ('excluded',    '점검제외'),
    ]

    project     = models.ForeignKey(
        AuditProject, on_delete=models.CASCADE,
        related_name='requirements', verbose_name='감리프로젝트'
    )
    code        = models.CharField('요구사항번호', max_length=20)
    category    = models.CharField('분류', max_length=10, choices=CATEGORY_CHOICES)
    name        = models.CharField('요구사항명', max_length=300)
    description = models.TextField('상세내용', blank=True)
    sla_target  = models.CharField('SLA 목표', max_length=200, blank=True,
                                   help_text='예: 장애접수 후 2시간 이내 현장 도착')
    is_additional = models.BooleanField('추가제안 항목', default=False,
                                        help_text='기술협상/추가제안으로 추가된 항목')
    status      = models.CharField('이행상태', max_length=20, choices=STATUS_CHOICES, default='not_started')
    evidence    = models.TextField('이행증빙', blank=True)
    notes       = models.TextField('비고', blank=True)
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        db_table        = 'audit_requirements'
        verbose_name    = '요구사항'
        ordering        = ['category', 'code']
        unique_together = [['project', 'code']]

    def __str__(self):
        return f'{self.code} {self.name}'


# ──────────────────────────────────────────────────
# 산출물 템플릿 (무엇이 나와야 하는지 정의)
# ──────────────────────────────────────────────────
class ArtifactTemplate(models.Model):
    AUDIT_PHASE_CHOICES = [
        ('initiation', '착수감리'),
        ('midterm',    '중간감리'),
        ('closing',    '종료감리'),
        ('all',        '전 단계'),
    ]
    SUBMIT_TIMING_CHOICES = [
        ('contract_10d', '계약 후 10일 이내'),
        ('monthly',      '매월'),
        ('quarterly',    '분기별 (분기 1회)'),
        ('on_occurrence','발생 시'),
        ('on_completion','사업완료 시'),
        ('as_needed',    '수시'),
    ]
    CATEGORY_CHOICES = [
        ('PM',  '사업관리'),
        ('IM',  '통합관리'),
        ('HR',  '운영인력'),
        ('SEC', '보안'),
        ('SVC', '서비스수행'),
        ('ADD', '추가제안'),
        ('FIN', '완료'),
    ]

    project        = models.ForeignKey(
        AuditProject, on_delete=models.CASCADE,
        related_name='artifact_templates', verbose_name='감리프로젝트'
    )
    requirement    = models.ForeignKey(
        Requirement, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='artifact_templates', verbose_name='연관요구사항'
    )
    audit_phase    = models.CharField('감리단계', max_length=20, choices=AUDIT_PHASE_CHOICES,
                                      help_text='이 산출물을 어느 감리단계에서 점검하는가')
    submit_timing  = models.CharField('제출시점', max_length=20, choices=SUBMIT_TIMING_CHOICES)
    category       = models.CharField('분류', max_length=10, choices=CATEGORY_CHOICES, default='PM')
    code           = models.CharField('산출물코드', max_length=50, blank=True)
    name           = models.CharField('산출물명', max_length=300)
    description    = models.TextField('설명 및 작성요령', blank=True)
    quantity_note  = models.CharField('수량/범위', max_length=200, blank=True,
                                      help_text='예: 학교별 1건, 월별 1건, 분기별 3회')
    is_required    = models.BooleanField('필수여부', default=True)
    is_additional  = models.BooleanField('추가제안', default=False)
    seq            = models.PositiveSmallIntegerField('순번', default=0)

    class Meta:
        db_table     = 'audit_artifact_templates'
        verbose_name = '산출물템플릿'
        ordering     = ['audit_phase', 'seq', 'code']

    def __str__(self):
        return f'[{self.get_audit_phase_display()}] {self.code} {self.name}'


# ──────────────────────────────────────────────────
# 산출물 (실제 제출된/작성 중인 산출물)
# ──────────────────────────────────────────────────
class Artifact(models.Model):
    STATUS_CHOICES = [
        ('pending',   '미작성'),
        ('draft',     '작성중'),
        ('submitted', '제출완료'),
        ('approved',  '승인완료'),
        ('rejected',  '반려'),
    ]

    project      = models.ForeignKey(
        AuditProject, on_delete=models.CASCADE,
        related_name='artifacts', verbose_name='감리프로젝트'
    )
    template     = models.ForeignKey(
        ArtifactTemplate, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='artifacts', verbose_name='산출물템플릿'
    )
    requirements = models.ManyToManyField(
        Requirement, blank=True,
        related_name='artifacts', verbose_name='연관요구사항'
    )
    code         = models.CharField('산출물코드', max_length=50, blank=True)
    name         = models.CharField('산출물명', max_length=300)
    audit_phase  = models.CharField('감리단계', max_length=20,
                                    choices=ArtifactTemplate.AUDIT_PHASE_CHOICES, blank=True)
    description  = models.TextField('설명', blank=True)
    status       = models.CharField('상태', max_length=20, choices=STATUS_CHOICES, default='pending')
    file         = models.FileField('첨부파일', upload_to='2026감리산출물/', blank=True, null=True)
    file_name    = models.CharField('파일명', max_length=255, blank=True)
    submitted_at = models.DateField('제출일', null=True, blank=True)
    submitted_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='submitted_artifacts', verbose_name='제출자'
    )
    occurrence_date = models.DateField('발생일/점검일', null=True, blank=True,
                                       help_text='장애조치: 장애발생일, 정기점검: 점검실시일, 월간보고: 해당월 1일')
    location_note   = models.CharField('장소/대상', max_length=200, blank=True,
                                        help_text='예: OOO학교, 동부교육지원청, 전체')
    notes        = models.TextField('비고', blank=True)
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        db_table     = 'audit_artifacts'
        verbose_name = '산출물'
        ordering     = ['audit_phase', 'code', 'name']

    def __str__(self):
        return f'[{self.audit_phase}] {self.name}'


# ──────────────────────────────────────────────────
# 감리 계획 (착수/중간/종료단계)
# ──────────────────────────────────────────────────
class AuditPlan(models.Model):
    PHASE_CHOICES = [
        ('initiation', '착수감리'),
        ('midterm',    '중간감리'),
        ('closing',    '종료감리'),
    ]
    STATUS_CHOICES = [
        ('planned',     '예정'),
        ('in_progress', '진행중'),
        ('completed',   '완료'),
    ]

    project       = models.ForeignKey(
        AuditProject, on_delete=models.CASCADE,
        related_name='audit_plans', verbose_name='감리프로젝트'
    )
    phase         = models.CharField('감리단계', max_length=20, choices=PHASE_CHOICES)
    status        = models.CharField('상태', max_length=20, choices=STATUS_CHOICES, default='planned')
    planned_start = models.DateField('예정시작일', null=True, blank=True)
    planned_end   = models.DateField('예정종료일', null=True, blank=True)
    actual_start  = models.DateField('실제시작일', null=True, blank=True)
    actual_end    = models.DateField('실제종료일', null=True, blank=True)
    kickoff_date  = models.DateField('착수회의일', null=True, blank=True)
    closing_date  = models.DateField('종료회의일', null=True, blank=True)
    location      = models.CharField('장소', max_length=200, blank=True)
    notes         = models.TextField('비고', blank=True)
    created_at    = models.DateTimeField(auto_now_add=True)
    updated_at    = models.DateTimeField(auto_now=True)

    class Meta:
        db_table     = 'audit_plans'
        verbose_name = '감리계획'
        ordering     = ['project', 'phase']

    def __str__(self):
        return f'{self.project.name} - {self.get_phase_display()}'

    @property
    def checklist_total(self):
        return self.checklist_items.count()

    @property
    def checklist_passed(self):
        return self.checklist_items.filter(result='pass').count()

    @property
    def checklist_pct(self):
        t = self.checklist_total
        return round(self.checklist_passed / t * 100) if t else 0


# ──────────────────────────────────────────────────
# 감리 체크리스트 항목 (단계별)
# ──────────────────────────────────────────────────
class ChecklistItem(models.Model):
    AREA_CHOICES = [
        ('A', 'A. 사업관리'),
        ('B', 'B. 서비스 수행'),
        ('C', 'C. 보안/품질'),
    ]
    PHASE_CHOICES = [
        ('plan',      '착수/계획'),
        ('execute',   '실행/통제'),
        ('close',     '종료/지원'),
    ]
    RESULT_CHOICES = [
        ('not_checked', '미점검'),
        ('pass',        '적합'),
        ('fail',        '부적합'),
        ('excluded',    '점검제외'),
    ]

    audit_plan   = models.ForeignKey(
        AuditPlan, on_delete=models.CASCADE,
        related_name='checklist_items', verbose_name='감리계획'
    )
    requirement  = models.ForeignKey(
        Requirement, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='checklist_items', verbose_name='연관요구사항'
    )
    area         = models.CharField('감리영역', max_length=5, choices=AREA_CHOICES)
    phase        = models.CharField('단계', max_length=20, choices=PHASE_CHOICES)
    seq          = models.PositiveSmallIntegerField('순번', default=1)
    description  = models.TextField('점검항목')
    check_point  = models.TextField('확인포인트', blank=True,
                                    help_text='감리원이 실제로 확인하는 방법/기준')
    result       = models.CharField('점검결과', max_length=20, choices=RESULT_CHOICES, default='not_checked')
    evidence     = models.TextField('확인내용/증빙', blank=True)
    finding      = models.TextField('발견사항', blank=True)
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        db_table     = 'audit_checklist_items'
        verbose_name = '감리체크리스트'
        ordering     = ['area', 'phase', 'seq']

    def __str__(self):
        return f'[{self.get_area_display()}] {self.description[:50]}'


# ──────────────────────────────────────────────────
# 시정조치
# ──────────────────────────────────────────────────
class CorrectiveAction(models.Model):
    TYPE_CHOICES = [
        ('mandatory',   '필수'),
        ('recommended', '권고'),
    ]
    STATUS_CHOICES = [
        ('open',        '미조치'),
        ('in_progress', '조치중'),
        ('completed',   '조치완료'),
        ('verified',    '확인완료'),
    ]

    checklist_item     = models.ForeignKey(
        ChecklistItem, on_delete=models.CASCADE,
        related_name='corrective_actions', verbose_name='체크리스트항목'
    )
    action_type        = models.CharField('조치유형', max_length=20, choices=TYPE_CHOICES, default='mandatory')
    issue_description  = models.TextField('지적사항')
    action_description = models.TextField('시정조치내용', blank=True)
    due_date           = models.DateField('조치기한', null=True, blank=True)
    status             = models.CharField('상태', max_length=20, choices=STATUS_CHOICES, default='open')
    evidence_file      = models.FileField('증빙파일', upload_to='2026감리산출물/시정조치/', blank=True, null=True)
    evidence_note      = models.TextField('증빙내용', blank=True)
    completed_at       = models.DateField('조치완료일', null=True, blank=True)
    completed_by       = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='completed_actions', verbose_name='조치자'
    )
    verified_at        = models.DateField('확인일', null=True, blank=True)
    verified_by        = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='verified_actions', verbose_name='확인자'
    )
    created_at         = models.DateTimeField(auto_now_add=True)
    updated_at         = models.DateTimeField(auto_now=True)

    class Meta:
        db_table     = 'audit_corrective_actions'
        verbose_name = '시정조치'
        ordering     = ['status', 'due_date']

    def __str__(self):
        return f'[{self.get_action_type_display()}] {self.issue_description[:50]}'


# ──────────────────────────────────────────────────
# 산출물 보관함 — 개별 파일 (소분류 단위)
# ──────────────────────────────────────────────────
class ArtifactFile(models.Model):
    """
    산출물 보관함의 실제 파일 레코드.
    ArtifactTemplate 1개에 N개 파일이 연결됨.

    파일명 규칙: {코드}_{장소 or 설명}_{날짜}.확장자
      예) SEN-IMR-004-01_OOO학교_20260612.pdf
          SEN-PMR-002-01_202605.hwp
          SEN-IMR-003-01_동부교육지원청_2026Q1.hwp

    NAS 폴더 구조: 2026감리산출물/{코드}/{파일명}
    """
    project         = models.ForeignKey(
        AuditProject, on_delete=models.CASCADE,
        related_name='artifact_files', verbose_name='감리프로젝트'
    )
    template        = models.ForeignKey(
        ArtifactTemplate, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='artifact_files', verbose_name='산출물템플릿'
    )
    file            = models.FileField(
        '파일', upload_to=artifact_file_upload_path, blank=True, null=True
    )
    file_name       = models.CharField('파일명', max_length=500)
    display_name    = models.CharField('표시명', max_length=500, blank=True,
                                       help_text='파일명에서 코드 제거한 표시용 이름')
    file_size       = models.PositiveIntegerField('파일크기(bytes)', default=0)
    occurrence_date = models.DateField('발생일/점검일', null=True, blank=True)
    location_note   = models.CharField('장소/대상', max_length=200, blank=True,
                                       help_text='학교명, 교육지원청, 전체 등')
    uploaded_by     = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='uploaded_artifact_files', verbose_name='등록자'
    )
    uploaded_at     = models.DateTimeField('등록일시', auto_now_add=True)
    is_scanned      = models.BooleanField('자동스캔 등록', default=False,
                                          help_text='NAS 폴더 스캔으로 자동 등록된 파일')
    notes           = models.TextField('비고', blank=True)

    class Meta:
        db_table     = 'audit_artifact_files'
        verbose_name = '산출물파일'
        ordering     = ['-occurrence_date', 'location_note', 'file_name']

    def __str__(self):
        return self.file_name

    @property
    def file_size_display(self):
        s = self.file_size
        if s >= 1024 * 1024:
            return f'{s / 1024 / 1024:.1f} MB'
        if s >= 1024:
            return f'{s / 1024:.0f} KB'
        return f'{s} B'

    @property
    def ext(self):
        return os.path.splitext(self.file_name)[1].lower()
