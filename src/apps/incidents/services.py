"""
incidents 비즈니스 로직 서비스
"""
from django.utils import timezone
from django.conf import settings
from django.db.models import Q
import httpx


def get_available_workers(incident):
    """배정 가능 인력 목록 반환 (같은 지원청 기준)"""
    from apps.accounts.models import User
    center = incident.school.support_center
    workers = User.objects.filter(
        role='worker', is_active=True,
        support_center=center
    ).select_related('current_location')
    return workers


def calculate_distance(lat1, lng1, lat2, lng2):
    """두 좌표 간 직선 거리 계산 (km) - Haversine formula"""
    import math
    R = 6371
    d_lat = math.radians(float(lat2) - float(lat1))
    d_lng = math.radians(float(lng2) - float(lng1))
    a = math.sin(d_lat/2)**2 + math.cos(math.radians(float(lat1))) * math.cos(math.radians(float(lat2))) * math.sin(d_lng/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return round(R * c, 2)


def get_best_worker(incident, workers):
    """거리·업무량 기반으로 최적 인력 선택

    우선순위:
    1. current_location GPS가 있으면 학교까지 거리 계산
    2. current_location 없으면 home GPS 사용
    3. GPS 없는 인력은 가장 낮은 우선순위
    4. 동일 거리 내에서는 현재 배정된 장애 수(업무량)가 적은 인력 우선
    """
    from .models import IncidentAssignment

    school = incident.school
    school_lat = float(school.lat) if school.lat else None
    school_lng = float(school.lng) if school.lng else None

    best_worker = None
    best_dist = None
    best_score = float('inf')

    for worker in workers:
        # 거리 계산
        loc = getattr(worker, 'current_location', None)
        if loc and loc.lat and loc.lng and school_lat is not None:
            dist = calculate_distance(loc.lat, loc.lng, school_lat, school_lng)
        elif worker.home_lat and worker.home_lng and school_lat is not None:
            dist = calculate_distance(worker.home_lat, worker.home_lng, school_lat, school_lng)
        else:
            dist = None

        # 업무량 패널티 (진행 중 장애 수 × 10km 가산)
        active_count = IncidentAssignment.objects.filter(
            worker=worker,
            incident__status__in=['assigned', 'in_progress']
        ).count()
        score = (dist if dist is not None else float('inf')) + active_count * 10

        if best_worker is None or score < best_score:
            best_score = score
            best_worker = worker
            best_dist = dist

    return best_worker, best_dist


def ai_assign_worker(incident):
    """FastAPI AI 서버에 인력 배정 요청"""
    ai_url = getattr(settings, 'AI_SERVER_URL', '')
    if not ai_url:
        return None
    try:
        payload = {
            'incident_id': incident.id,
            'school_lat': float(incident.school.lat or 0),
            'school_lng': float(incident.school.lng or 0),
            'center_code': incident.school.support_center.code,
            'category': incident.category.code,
            'priority': incident.priority,
        }
        resp = httpx.post(f'{ai_url}/api/assignment/recommend/', json=payload, timeout=10)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None


def create_assignment(incident, worker, assigned_by, is_ai=False, distance_km=None, eta_minutes=None):
    """장애 인력 배정 생성"""
    from .models import IncidentAssignment, IncidentStatusHistory
    assign = IncidentAssignment.objects.create(
        incident=incident,
        worker=worker,
        assigned_by=assigned_by,
        is_ai_assigned=is_ai,
        distance_km=distance_km,
        eta_minutes=eta_minutes,
    )
    now = timezone.now()
    incident.status = 'assigned'
    incident.assigned_at = now
    incident.save(update_fields=['status', 'assigned_at'])
    IncidentStatusHistory.objects.create(
        incident=incident, from_status='received', to_status='assigned',
        changed_by=assigned_by, note=f"{'AI자동' if is_ai else '수동'} 배정: {worker.name}"
    )
    # 업무 일정 자동 등록
    _create_incident_schedule(assign, now, eta_minutes, assigned_by)
    return assign


def _create_incident_schedule(assignment, assigned_at, eta_minutes, created_by):
    """장애 배정 시 WorkSchedule 자동 생성"""
    from apps.workforce.models import WorkSchedule, WorkScheduleType
    try:
        schedule_type = WorkScheduleType.objects.get(code='incident')
    except WorkScheduleType.DoesNotExist:
        return

    incident = assignment.incident
    category_name = incident.category.name if incident.category else '장애처리'
    school_name = incident.school.name if incident.school else ''

    # 종료일시: ETA 기준, 없으면 접수 후 4시간으로 추정
    duration_minutes = (eta_minutes or 0) + 120  # 이동 + 처리 2시간
    end_dt = assigned_at + timezone.timedelta(minutes=duration_minutes)

    title = f"[장애] {school_name} - {category_name} ({incident.incident_number})"

    description_parts = [
        f"장애번호: {incident.incident_number}",
        f"학교: {school_name}",
        f"분류: {category_name}",
        f"긴급도: {incident.get_priority_display()}",
        f"요청내용: {incident.description[:100]}{'...' if len(incident.description) > 100 else ''}",
    ]
    if eta_minutes:
        description_parts.append(f"예상도착: {eta_minutes}분")

    WorkSchedule.objects.create(
        worker=assignment.worker,
        schedule_type=schedule_type,
        school=incident.school,
        incident=incident,
        title=title,
        description='\n'.join(description_parts),
        start_dt=assigned_at,
        end_dt=end_dt,
        status='planned',
        created_by=created_by,
    )


def generate_incident_pdf(incident_id):
    """장애처리보고서 PDF 생성 (Celery Task에서 호출)"""
    from .models import Incident, IncidentCategory, IncidentSubcategory
    from django.db.models import Prefetch
    incident = Incident.objects.select_related(
        'school', 'school__support_center', 'category', 'subcategory', 'received_by'
    ).prefetch_related('assignments__worker', 'photos').get(id=incident_id)

    from django.template.loader import render_to_string
    from django.utils import timezone
    import weasyprint, os

    # 처리소요시간 계산
    if incident.completed_at:
        elapsed = int((incident.completed_at - incident.received_at).total_seconds() / 60)
        elapsed_display = f"{elapsed // 60}시간 {elapsed % 60}분" if elapsed >= 60 else f"{elapsed}분"
    else:
        elapsed_display = '-'

    # 처리자 (첫 번째 배정 인력)
    first_assignment = incident.assignments.select_related('worker').filter(is_accepted=True).first() \
                       or incident.assignments.select_related('worker').first()

    # 전체 대분류+소분류 (체크박스 렌더링용)
    all_categories = IncidentCategory.objects.prefetch_related(
        Prefetch('subcategories', queryset=IncidentSubcategory.objects.filter(is_active=True).order_by('order'))
    ).filter(is_active=True).order_by('order')

    html = render_to_string('incidents/pdf_report.html', {
        'incident':         incident,
        'assignments':      incident.assignments.select_related('worker').all(),
        'photos':           incident.photos.all(),
        'first_assignment': first_assignment,
        'elapsed_display':  elapsed_display,
        'all_categories':   all_categories,
        'now':              timezone.now(),
    })
    nas_path = os.path.join(
        settings.NAS_OUTPUT_ROOT, '장애처리보고서',
        f'장애처리보고서_{incident.school.name}_{incident.incident_number}.pdf'
    )
    os.makedirs(os.path.dirname(nas_path), exist_ok=True)
    weasyprint.HTML(string=html).write_pdf(nas_path)
    incident.report_pdf_path = nas_path
    incident.save(update_fields=['report_pdf_path'])
    return nas_path


def generate_work_order_pdf(wo):
    """작업지시서 PDF 생성 → NAS 저장"""
    from django.template.loader import render_to_string
    from django.utils import timezone
    import weasyprint, os

    wo = type(wo).objects.select_related(
        'incident__school__support_center', 'incident__category',
        'incident__location_building', 'incident__location_floor', 'incident__location_room',
        'school__support_center', 'assigned_to', 'created_by', 'confirmed_by'
    ).get(id=wo.id)

    html = render_to_string('incidents/pdf_work_order.html', {
        'wo': wo,
        'now': timezone.now(),
    })
    nas_path = os.path.join(
        settings.NAS_OUTPUT_ROOT, '작업지시서',
        f'작업지시서_{wo.school.name}_{wo.work_order_number}.pdf'
    )
    os.makedirs(os.path.dirname(nas_path), exist_ok=True)
    weasyprint.HTML(string=html).write_pdf(nas_path)
    wo.pdf_path = nas_path
    wo.save(update_fields=['pdf_path'])
    return nas_path


def generate_delay_reason_pdf(delay_reason):
    """지연처리사유서 PDF 생성 → NAS 저장"""
    from .models import IncidentSLA
    from django.template.loader import render_to_string
    from django.utils import timezone
    import weasyprint, os

    incident = delay_reason.incident

    # 처리자
    first_assignment = incident.assignments.select_related('worker').filter(is_accepted=True).first() \
                       or incident.assignments.select_related('worker').first()

    # SLA 초과시간 계산
    sla_target = None
    exceeded_display = '-'
    try:
        sla = incident.sla
        sla_target = sla.resolve_target
        if incident.completed_at and sla_target:
            diff_min = int((incident.completed_at - sla_target).total_seconds() / 60)
            if diff_min > 0:
                exceeded_display = f"{diff_min // 60}시간 {diff_min % 60}분 초과"
            else:
                exceeded_display = '기준 이내'
    except IncidentSLA.DoesNotExist:
        pass

    html = render_to_string('incidents/pdf_delay_reason.html', {
        'incident':         incident,
        'delay_reason':     delay_reason,
        'first_assignment': first_assignment,
        'sla_target':       sla_target,
        'exceeded_display': exceeded_display,
        'now':              timezone.now(),
    })
    nas_path = os.path.join(
        settings.NAS_OUTPUT_ROOT, '지연처리 사유서',
        f'지연처리사유서_{incident.school.name}_{incident.incident_number}.pdf'
    )
    os.makedirs(os.path.dirname(nas_path), exist_ok=True)
    weasyprint.HTML(string=html).write_pdf(nas_path)
    delay_reason.pdf_path = nas_path
    delay_reason.save(update_fields=['pdf_path'])
    return nas_path


def send_satisfaction_survey(incident):
    """만족도 조사 문자 발송 (장애완료 시 담당 선생님에게)"""
    import secrets
    from django.conf import settings
    from apps.statistics.models import SatisfactionSurvey
    from .sms_service import send_sms

    phone = incident.requester_phone
    if not phone:
        return  # 연락처 없으면 발송 불가

    token = secrets.token_urlsafe(16)
    survey = SatisfactionSurvey.objects.create(
        incident=incident,
        sent_to=phone,
        token=token,
    )

    # 만족도 응답 URL 생성
    base_url = getattr(settings, 'SITE_URL', 'http://112.187.158.4/npms')
    survey_url = f"{base_url}/survey/respond/?token={token}"

    school_name = incident.school.name if incident.school else '학교'
    message = (
        f"[NPMS] 네트워크 장애처리 만족도 조사\n"
        f"학교: {school_name}\n"
        f"접수: #{incident.incident_number}\n"
        f"처리가 완료되었습니다.\n"
        f"서비스 만족도를 평가해 주세요:\n"
        f"{survey_url}"
    )
    sent = send_sms(phone, message)
    if sent:
        survey.status = 'sent'
        survey.save(update_fields=['status'])

    incident.satisfaction_sent = True
    incident.save(update_fields=['satisfaction_sent'])
