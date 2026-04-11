"""
알림 자동 생성 시그널
- 장애 접수 → 관리자/슈퍼관리자 알림
- 장애 완료 → 접수자 알림
- 정기점검 보고서 완료 → 관리자 알림
- WBS 항목 진척 100% → 관리자 알림
"""
import logging
from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


# ── 장애 접수 / 완료 알림 ─────────────────────────────────
@receiver(post_save, sender='incidents.Incident')
def incident_notify(sender, instance, created, **kwargs):
    try:
        from .models import Notification
        from apps.accounts.models import User

        if created:
            # 새 장애 접수 → 관리자 전체 알림
            managers = User.objects.filter(
                role__in=['superadmin', 'admin'], is_active=True
            )
            school = instance.school.name if instance.school else '—'
            Notification.broadcast(
                managers,
                title=f'새 장애 접수: {school}',
                message=instance.fault_detail[:80] if instance.fault_detail else '',
                ntype='incident', level='warning',
                link=f'/npms/incidents/{instance.pk}/',
            )

        elif instance.status == 'completed' and instance.received_by:
            # 장애 완료 → 최초 접수자 알림
            Notification.push(
                user=instance.received_by,
                title=f'장애 처리 완료: {instance.school.name if instance.school else ""}',
                message=f'접수번호 {instance.incident_number}',
                ntype='incident', level='success',
                link=f'/npms/incidents/{instance.pk}/',
            )
    except Exception as e:
        logger.warning('장애 알림 시그널 실패 incident=%s: %s', instance.pk, e)


# ── 정기점검 보고서 완료 알림 ─────────────────────────────
@receiver(post_save, sender='reports.Report')
def report_notify(sender, instance, created, **kwargs):
    try:
        if instance.status != 'completed':
            return
        from .models import Notification
        from apps.accounts.models import User

        managers = User.objects.filter(
            role__in=['superadmin', 'admin'], is_active=True
        )
        school = instance.school.name if instance.school else '—'
        Notification.broadcast(
            managers,
            title=f'보고서 완료: {school} — {instance.title}',
            ntype='report', level='success',
            link='/npms/reports/',
        )
    except Exception as e:
        logger.warning('보고서 알림 시그널 실패 report=%s: %s', instance.pk, e)


# ── WBS 항목 100% 완료 알림 ──────────────────────────────
@receiver(post_save, sender='wbs.WBSItem')
def wbs_notify(sender, instance, created, **kwargs):
    try:
        if created or instance.progress != 100:
            return
        from .models import Notification
        from apps.accounts.models import User

        managers = User.objects.filter(
            role__in=['superadmin', 'admin'], is_active=True
        )
        Notification.broadcast(
            managers,
            title=f'WBS 완료: [{instance.code}] {instance.name}',
            ntype='wbs', level='success',
            link='/npms/wbs/',
        )
    except Exception as e:
        logger.warning('WBS 알림 시그널 실패 item=%s: %s', instance.pk, e)
