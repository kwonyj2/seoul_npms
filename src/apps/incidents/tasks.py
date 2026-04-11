import logging
from config.celery import app as celery_app
from django.utils import timezone

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=2)
def send_incident_sms_task(self, incident_id: int, event: str):
    """
    장애 상태 변경 SMS 발송
    event: 'assigned' | 'completed' | 'escalated'
    """
    try:
        from .models import Incident
        from .sms_service import (
            send_sms, make_incident_assigned_msg, make_incident_completed_msg
        )
        incident = Incident.objects.select_related('school', 'category').prefetch_related('assignments__worker').get(pk=incident_id)

        if event == 'assigned':
            # 가장 최근 배정 인력
            assignment = incident.assignments.select_related('worker').filter(is_accepted=True).first() \
                         or incident.assignments.select_related('worker').first()
            if assignment and assignment.worker:
                phone = getattr(assignment.worker, 'phone', '') or ''
                if phone:
                    msg = make_incident_assigned_msg(incident)
                    send_sms(phone, msg)
        elif event == 'completed' and incident.school:
            # 학교 담당자 번호 (담당자 필드 없으면 건너뜀)
            contact = getattr(incident.school, 'contact_phone', '') or ''
            if contact:
                msg = make_incident_completed_msg(incident)
                send_sms(contact, msg)
    except Exception as exc:
        raise self.retry(exc=exc, countdown=30)


@celery_app.task(bind=True, max_retries=2)
def send_network_event_sms_task(self, event_id: int):
    """네트워크 이벤트 SMS 발송 (critical/major 이벤트만)"""
    try:
        from apps.network.models import NetworkEvent
        from .sms_service import send_sms, make_network_event_msg
        from apps.accounts.models import User
        event = NetworkEvent.objects.select_related('device', 'device__school').get(pk=event_id)
        if event.severity not in ('critical', 'major'):
            return
        msg = make_network_event_msg(event)
        # 관리자 계정에 SMS 발송
        admins = User.objects.filter(role__in=['admin', 'superadmin'], is_active=True).exclude(phone='')
        for admin in admins[:5]:
            send_sms(admin.phone, msg)
    except Exception as exc:
        raise self.retry(exc=exc, countdown=30)


@celery_app.task(bind=True, max_retries=3)
def generate_incident_pdf_task(self, incident_id):
    """장애처리보고서 PDF 비동기 생성"""
    try:
        from .services import generate_incident_pdf
        path = generate_incident_pdf(incident_id)
        return {'status': 'success', 'path': path}
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)


@celery_app.task
def send_satisfaction_survey_task(incident_id):
    """만족도 조사 발송"""
    from .models import Incident
    from .services import send_satisfaction_survey
    try:
        incident = Incident.objects.get(id=incident_id)
        send_satisfaction_survey(incident)
    except Incident.DoesNotExist:
        pass


@celery_app.task
def check_sla_violations():
    """SLA 위반 체크 (Celery Beat - 주기적 실행)"""
    from .models import Incident, IncidentSLA
    from django.db.models import Q
    now = timezone.now()
    # 미완료 장애 중 SLA 초과 건 체크
    overdue = Incident.objects.filter(
        ~Q(status='completed'),
        ~Q(status='cancelled'),
    ).select_related('sla', 'school')
    alerts = []
    for incident in overdue:
        try:
            sla = incident.sla
            if now > sla.arrive_target and incident.arrived_at is None:
                alerts.append({'type': 'arrival', 'incident': incident.incident_number})
            if now > sla.resolve_target:
                alerts.append({'type': 'resolve', 'incident': incident.incident_number})
        except Exception as e:
            logger.warning('SLA 알림 확인 실패 incident=%s: %s', incident.incident_number, e)
    # WebSocket으로 알림 전송 (구현 시 연동)
    return {'alerts_count': len(alerts), 'alerts': alerts}


@celery_app.task
def update_daily_statistics():
    """일별 통계 업데이트 (Celery Beat - 매일 자정)"""
    from .models import Incident
    from apps.statistics.models import StatisticsDaily
    from django.db.models import Count, Avg
    today = timezone.localdate()
    incidents = Incident.objects.filter(received_at__date=today)
    stats, _ = StatisticsDaily.objects.update_or_create(
        stat_date=today,
        defaults={
            'total_incidents':      incidents.count(),
            'completed_incidents':  incidents.filter(status='completed').count(),
            'sla_arrival_ok':       incidents.filter(sla_arrival_ok=True).count(),
            'sla_resolve_ok':       incidents.filter(sla_resolve_ok=True).count(),
        }
    )
    return {'date': str(today), 'total': stats.total_incidents}
