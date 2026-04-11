"""
장애(Incident) 상태 변경 시 SMS 알림 트리거
"""
from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender='incidents.Incident')
def on_incident_saved(sender, instance, created, update_fields, **kwargs):
    """
    장애 저장 시 SMS 알림 + 업무 일정 상태 동기화
    - 배정(assigned): 담당 기사에게
    - 완료(completed): 학교 담당자에게, WorkSchedule → completed
    - 취소(cancelled): WorkSchedule → cancelled
    """
    from .tasks import send_incident_sms_task

    status = instance.status
    if update_fields and 'status' not in update_fields and 'assigned_worker' not in update_fields:
        return  # 상태/배정 필드 외 변경은 무시

    if status == 'assigned':
        send_incident_sms_task.delay(instance.pk, 'assigned')
    elif status == 'completed':
        send_incident_sms_task.delay(instance.pk, 'completed')
        # 처리보고서 PDF 자동 생성
        from .tasks import generate_incident_pdf_task
        generate_incident_pdf_task.delay(instance.pk)
        # 만족도 조사 SMS 발송 (아직 발송되지 않은 경우)
        if not getattr(instance, 'satisfaction_sent', False):
            from .tasks import send_satisfaction_survey_task
            send_satisfaction_survey_task.delay(instance.pk)
        # 연관 업무 일정 완료 처리
        _sync_schedules_on_incident_status(instance, 'completed')
    elif status == 'cancelled':
        # 연관 업무 일정 취소 처리
        _sync_schedules_on_incident_status(instance, 'cancelled')


def _sync_schedules_on_incident_status(incident, new_status):
    """장애 완료/취소 시 연관 WorkSchedule 상태 동기화"""
    from django.utils import timezone
    from apps.workforce.models import WorkSchedule
    qs = WorkSchedule.objects.filter(incident=incident).exclude(status__in=['completed', 'cancelled'])
    update_kwargs = {'status': new_status}
    if new_status == 'completed' and incident.completed_at:
        update_kwargs['end_dt'] = incident.completed_at
    qs.update(**update_kwargs)


@receiver(post_save, sender='network.NetworkEvent')
def on_network_event_created(sender, instance, created, **kwargs):
    """신규 네트워크 이벤트 생성 시 SMS 알림"""
    if not created:
        return
    from .tasks import send_network_event_sms_task
    send_network_event_sms_task.delay(instance.pk)
