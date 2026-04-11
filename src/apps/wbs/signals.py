"""
WBS 자동 진척 연동 시그널
- InspectionPlan / SchoolInspection 저장 → 연결된 WBSItem 진척 갱신
- ArtifactFile 생성 → 연결된 WBSItem 100%
"""
from django.db.models.signals import post_save
from django.dispatch import receiver


def _bubble_up(item):
    """리프 → 루트 방향으로 부모 노드 가중평균 재계산"""
    parent = item.parent
    while parent is not None:
        if parent.progress_source == 'children':
            parent.recalculate_from_children()
        parent = parent.parent


@receiver(post_save, sender='progress.InspectionPlan')
def sync_inspection_plan(sender, instance, **kwargs):
    from apps.wbs.models import WBSItem
    items = WBSItem.objects.filter(linked_inspection=instance, progress_source='inspection')
    for item in items:
        item.progress = instance.progress_pct
        item.save(update_fields=['progress', 'updated_at'])
        _bubble_up(item)


@receiver(post_save, sender='progress.SchoolInspection')
def sync_school_inspection(sender, instance, **kwargs):
    """학교별 점검 완료 시 → 상위 InspectionPlan progress_pct 변경 → WBS 갱신"""
    from apps.wbs.models import WBSItem
    plan = instance.plan
    items = WBSItem.objects.filter(linked_inspection=plan, progress_source='inspection')
    pct = plan.progress_pct
    for item in items:
        item.progress = pct
        item.save(update_fields=['progress', 'updated_at'])
        _bubble_up(item)


@receiver(post_save, sender='audit.ArtifactFile')
def sync_artifact_file(sender, instance, **kwargs):
    from apps.wbs.models import WBSItem
    if not instance.template:
        return
    items = WBSItem.objects.filter(
        linked_template=instance.template,
        progress_source='artifact'
    )
    for item in items:
        item.progress = 100
        item.save(update_fields=['progress', 'updated_at'])
        _bubble_up(item)
