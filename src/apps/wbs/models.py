"""
WBS (Work Breakdown Structure) 모델
- 2026 사업 과업 트리 구조
- 진척 소스: 수동 / 산출물 등록 / 점검 진척 / 장애처리 / 하위 자동집계
"""
from django.db import models


class WBSItem(models.Model):
    # ── 진척 소스 ──────────────────────────────
    PROGRESS_SOURCE_CHOICES = [
        ('manual',     '수동 입력'),
        ('artifact',   '산출물 등록'),
        ('inspection', '점검 진척'),
        ('incident',   '장애처리 건수'),
        ('children',   '하위 항목 자동집계'),
    ]

    # ── 페이즈 ────────────────────────────────
    PHASE_CHOICES = [
        ('plan',    '계획'),
        ('execute', '수행'),
        ('close',   '종료'),
    ]

    # ── 기본 필드 ─────────────────────────────
    project    = models.ForeignKey(
        'audit.AuditProject', on_delete=models.CASCADE,
        related_name='wbs_items', verbose_name='감리 프로젝트'
    )
    code       = models.CharField('WBS 코드', max_length=20)   # 예: 1.2.3
    depth      = models.PositiveSmallIntegerField('깊이')       # 1=대, 2=중, 3=소
    parent     = models.ForeignKey(
        'self', on_delete=models.CASCADE, null=True, blank=True,
        related_name='children', verbose_name='상위 항목'
    )
    phase      = models.CharField('단계', max_length=10, choices=PHASE_CHOICES)
    seq        = models.PositiveSmallIntegerField('정렬순서', default=0)
    name       = models.CharField('작업명', max_length=200)
    assignee   = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='wbs_items', verbose_name='담당자'
    )
    weight     = models.DecimalField('가중치', max_digits=6, decimal_places=4, default=0)

    # ── 일정 ─────────────────────────────────
    planned_start = models.DateField('계획 시작일', null=True, blank=True)
    planned_end   = models.DateField('계획 종료일', null=True, blank=True)
    actual_start  = models.DateField('실적 시작일', null=True, blank=True)
    actual_end    = models.DateField('실적 종료일', null=True, blank=True)

    # ── 진척 ─────────────────────────────────
    progress        = models.PositiveSmallIntegerField('진척률(%)', default=0)
    progress_source = models.CharField(
        '진척 소스', max_length=20,
        choices=PROGRESS_SOURCE_CHOICES, default='manual'
    )

    # 소스별 연계 (택1)
    linked_template   = models.ForeignKey(
        'audit.ArtifactTemplate', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='wbs_items', verbose_name='연계 산출물 템플릿'
    )
    linked_inspection = models.ForeignKey(
        'progress.InspectionPlan', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='wbs_items', verbose_name='연계 점검계획'
    )
    # incident 소스: 기간 기반 집계 (FK 없이 planned_start/end 사용)

    # ── 주간 계획/실적 ────────────────────────
    this_week_plan   = models.TextField('금주 계획', blank=True)
    this_week_actual = models.TextField('금주 실적', blank=True)
    next_week_plan   = models.TextField('차주 계획', blank=True)

    is_milestone = models.BooleanField('마일스톤', default=False)
    notes        = models.TextField('비고', blank=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        db_table        = 'wbs_items'
        verbose_name    = 'WBS 항목'
        ordering        = ['seq']
        unique_together = [['project', 'code']]

    def __str__(self):
        return f'[{self.code}] {self.name}'

    # ── 헬퍼 ─────────────────────────────────
    def recalculate_from_children(self):
        """하위 항목 가중 평균으로 진척률 재계산 (children 소스 전용)"""
        kids = list(self.children.all())
        if not kids:
            return
        total_weight = sum(float(k.weight) for k in kids)
        if total_weight == 0:
            return
        weighted = sum(float(k.weight) * k.progress for k in kids)
        self.progress = round(weighted / total_weight)
        self.save(update_fields=['progress', 'updated_at'])


class WBSProgressHistory(models.Model):
    """WBS 진척 이력 — 주차별 진척률 변화 자동 기록"""
    item       = models.ForeignKey(WBSItem, on_delete=models.CASCADE,
                                   related_name='history', verbose_name='WBS 항목')
    week_date  = models.DateField('기준일 (주 시작일)')
    progress   = models.PositiveSmallIntegerField('진척률(%)')
    planned_progress = models.DecimalField('계획진척률(%)', max_digits=5, decimal_places=1, default=0)
    note       = models.TextField('비고', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'wbs_progress_history'
        verbose_name = 'WBS 진척 이력'
        unique_together = [['item', 'week_date']]
        ordering = ['-week_date']

    def __str__(self):
        return f'{self.item.code} {self.week_date} {self.progress}%'
