from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.utils import timezone
from django.db.models import Count, Avg, Q, Sum, F
from django.conf import settings


def vworld_sdk_proxy(request):
    """브이월드 SDK JS를 서버 사이드에서 프록시 (Referer 인증 + document.write 패치)"""
    import httpx
    api_key = getattr(settings, 'VWORLD_API_KEY', '')
    scheme = 'https' if request.is_secure() else 'http'
    origin = f"{scheme}://{request.get_host()}"

    # document.write 차단 우회 패치 — 브라우저가 cross-site document.write를 막으므로
    # <script> 태그를 createElement 방식으로 교체하는 shim을 앞에 주입
    patch = """
(function(){
  var _orig = document.write.bind(document);
  document.write = function(html){
    var tmp = document.createElement('div');
    tmp.innerHTML = html;
    var scripts = tmp.querySelectorAll('script');
    if(scripts.length){
      scripts.forEach(function(s){
        var el = document.createElement('script');
        el.type = 'text/javascript';
        if(s.src){ el.src = s.src; el.async = false; }
        else { el.textContent = s.textContent; }
        document.head.appendChild(el);
      });
    } else {
      document.head.insertAdjacentHTML('beforeend', html);
    }
  };
})();
"""
    try:
        resp = httpx.get(
            f'https://map.vworld.kr/js/vworldMapInit.js.do?version=2.0&apiKey={api_key}',
            headers={'Referer': origin + '/'},
            timeout=10,
        )
        content = patch + resp.text
        return HttpResponse(content, content_type='application/javascript')
    except Exception:
        return HttpResponse('', content_type='application/javascript')


def get_dashboard_data():
    """대시보드 데이터 반환 (WebSocket 컨슈머에서도 사용)"""
    from apps.incidents.models import Incident
    from apps.accounts.models import User, UserSession
    from apps.schools.models import School
    from datetime import timedelta

    now   = timezone.localtime(timezone.now())
    today = now.date()
    cutoff = now - timedelta(minutes=60)

    incidents = Incident.objects.all()
    inc_summary = {
        'total':      incidents.count(),
        'received':   incidents.filter(status='received').count(),
        'assigned':   incidents.filter(status='assigned').count(),
        'processing': incidents.filter(status__in=['moving','arrived','processing']).count(),
        'completed':  incidents.filter(status='completed').count(),
        'today':      incidents.filter(received_at__date=today).count(),
        'today_completed': incidents.filter(received_at__date=today, status='completed').count(),
    }
    from datetime import timedelta as _td
    sla_resolve_h = getattr(settings, 'SLA_RESOLVE_HOURS', 8)
    month_start = today.replace(day=1)
    month_inc   = incidents.filter(status='completed', completed_at__date__gte=month_start)
    total_m = month_inc.count()
    sla_ok  = month_inc.filter(
        completed_at__lte=F('received_at') + _td(hours=sla_resolve_h)
    ).count()
    inc_summary['sla_rate'] = round(sla_ok / total_m * 100, 1) if total_m > 0 else None

    online_sessions = UserSession.objects.filter(is_active=True, last_active__gte=cutoff)
    online_users    = list(online_sessions.select_related('user').values(
        'user__name', 'user__role', 'current_page', 'last_active', 'ip_address'
    ).order_by('-last_active')[:50])
    for u in online_users:
        u['last_active'] = u['last_active'].strftime('%H:%M') if u['last_active'] else ''
        u['role_display'] = dict([
            ('superadmin','슈퍼관리자'),('admin','관리자'),
            ('customer','학교담당자'),('worker','현장기사'),('resident','상주인력'),
        ]).get(u['user__role'], u['user__role'])
    active_workers  = User.objects.filter(role='worker', is_active=True).count()
    school_count    = School.objects.filter(is_active=True).count()

    # 미완료 전체 + 오늘 완료건 (오늘 자정까지 유지)
    from django.db.models import Case, When, IntegerField, Value
    recent = list(
        incidents.filter(
            Q(status__in=['received', 'assigned', 'moving', 'arrived', 'processing']) |
            Q(status='completed', received_at__date=today)
        ).select_related('school', 'school__support_center', 'category')
        .annotate(sort_grp=Case(
            When(status='completed', then=Value(1)),
            default=Value(0),
            output_field=IntegerField()
        ))
        .order_by('sort_grp', '-received_at')[:50]
    )

    recent_list = [{
        'id':              i.id,
        'incident_number': i.incident_number,
        'school_name':     i.school.name,
        'center_name':     i.school.support_center.name,
        'status':          i.status,
        'priority':        i.priority,
        'elapsed_min':     i.get_elapsed_minutes(),
    } for i in recent]

    return {
        'school_count':    school_count,
        'active_workers':  active_workers,
        'online_count':    online_sessions.count(),
        'online_users':    online_users,
        'incidents':       inc_summary,
        'recent_incidents': recent_list,
        'timestamp':       now.strftime('%Y-%m-%d %H:%M:%S'),
    }


RELATED_SITES = [
    ('서울시교육청',      'https://www.sen.go.kr'),
    ('동부교육지원청',    'https://dbedu.sen.go.kr'),
    ('서부교육지원청',    'https://sbedu.sen.go.kr'),
    ('남부교육지원청',    'https://nbedu.sen.go.kr'),
    ('북부교육지원청',    'https://bbedu.sen.go.kr'),
    ('중부교육지원청',    'https://jbedu.sen.go.kr'),
    ('강동송파교육지원청','https://gdspedu.sen.go.kr'),
    ('강서양천교육지원청','https://gsycedu.sen.go.kr'),
    ('강남서초교육지원청','https://gnscedu.sen.go.kr'),
    ('동작관악교육지원청','https://dgedu.sen.go.kr'),
    ('성동광진교육지원청','https://sdgjedu.sen.go.kr'),
    ('성북강북교육지원청','https://sbgbedu.sen.go.kr'),
]


@login_required
def index(request):
    """메인 대시보드"""
    return render(request, 'dashboard/index.html', {'related_sites': RELATED_SITES})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dashboard_summary(request):
    """대시보드 전체 요약 데이터 API"""
    from apps.incidents.models import Incident
    from apps.accounts.models import User, UserSession
    from datetime import timedelta

    now = timezone.localtime(timezone.now())
    today = now.date()
    cutoff = now - timedelta(minutes=60)

    # 장애 현황
    incidents = Incident.objects.all()
    inc_summary = {
        'total':      incidents.count(),
        'received':   incidents.filter(status='received').count(),
        'assigned':   incidents.filter(status='assigned').count(),
        'processing': incidents.filter(status__in=['moving','arrived','processing']).count(),
        'completed':  incidents.filter(status='completed').count(),
        'today':      incidents.filter(received_at__date=today).count(),
        'today_completed': incidents.filter(received_at__date=today, status='completed').count(),
    }

    # SLA 준수율 (이번달) — completed_at vs received_at+기준시간 직접 비교
    from datetime import timedelta as _td
    sla_resolve_h = getattr(settings, 'SLA_RESOLVE_HOURS', 8)
    month_start = today.replace(day=1)
    month_inc   = incidents.filter(status='completed', completed_at__date__gte=month_start)
    total_m     = month_inc.count()
    sla_ok      = month_inc.filter(
        completed_at__lte=F('received_at') + _td(hours=sla_resolve_h)
    ).count()
    inc_summary['sla_rate'] = round(sla_ok / total_m * 100, 1) if total_m > 0 else None

    # 현재 접속자 (60분 이내 활동)
    ROLE_KR = {'superadmin':'슈퍼관리자','admin':'관리자','customer':'학교담당자',
               'worker':'현장기사','resident':'상주인력'}
    online_sessions = UserSession.objects.filter(is_active=True, last_active__gte=cutoff)
    raw_users = list(online_sessions.select_related('user').values(
        'user__name', 'user__role', 'current_page', 'last_active', 'ip_address'
    ).order_by('-last_active')[:50])
    online_users = []
    for u in raw_users:
        online_users.append({
            'user__name':   u['user__name'],
            'user__role':   u['user__role'],
            'role_display': ROLE_KR.get(u['user__role'], u['user__role']),
            'current_page': u['current_page'] or '접속중',
            'last_active':  u['last_active'].strftime('%H:%M') if u['last_active'] else '',
            'ip_address':   u['ip_address'] or '',
        })

    # 활성 인력 수
    active_workers = User.objects.filter(role='worker', is_active=True).count()

    # 학교 수
    from apps.schools.models import School
    school_count = School.objects.filter(is_active=True).count()

    # 미완료 전체 + 오늘 완료건 — 완료는 하단 정렬, 최대 50건
    from django.db.models import Case, When, IntegerField, Value
    recent = list(
        incidents.filter(
            Q(status__in=['received', 'assigned', 'moving', 'arrived', 'processing']) |
            Q(status='completed', received_at__date=today)
        ).select_related('school', 'school__support_center', 'category')
        .annotate(sort_grp=Case(
            When(status='completed', then=Value(1)),
            default=Value(0),
            output_field=IntegerField()
        ))
        .order_by('sort_grp', '-received_at')[:50]
    )

    recent_list = [{
        'id':              i.id,
        'incident_number': i.incident_number,
        'school_name':     i.school.name,
        'school_id':       i.school.id,
        'school_lat':      float(i.school.lat)  if i.school.lat  else None,
        'school_lng':      float(i.school.lng)  if i.school.lng  else None,
        'center_name':     i.school.support_center.name,
        'category':        i.category.name,
        'status':          i.status,
        'priority':        i.priority,
        'received_at':     i.received_at.strftime('%m-%d %H:%M'),
        'elapsed_min':     i.get_elapsed_minutes(),
    } for i in recent]

    # SLA 경고: 미완료 장애 중 SLA 초과건
    # IncidentSLA.arrival_target / resolve_target (업무시간 기준) 우선 사용
    # SLA 레코드 없는 구건은 received_at + 고정시간으로 fallback
    from apps.incidents.models import IncidentSLA
    from datetime import timedelta

    sla_arrival_hours = getattr(settings, 'SLA_ARRIVAL_HOURS', 2)
    sla_resolve_hours = getattr(settings, 'SLA_RESOLVE_HOURS', 8)

    # IncidentSLA 가 있는 건: resolve_target < now (미완료)
    sla_resolve_qs = (
        IncidentSLA.objects
        .filter(resolve_target__lt=now)
        .exclude(incident__status__in=['completed', 'cancelled'])
        .select_related('incident', 'incident__school')
        .order_by('resolve_target')
    )
    sla_arrival_qs = (
        IncidentSLA.objects
        .filter(arrival_target__lt=now, arrival_actual__isnull=True)
        .exclude(incident__status__in=['completed', 'cancelled'])
        .select_related('incident', 'incident__school')
        .order_by('arrival_target')
    )

    # IncidentSLA 없는 구건 fallback
    sla_incident_ids = set(
        IncidentSLA.objects.values_list('incident_id', flat=True)
    )
    active_nosla = (
        incidents
        .exclude(status__in=['completed', 'cancelled'])
        .exclude(id__in=sla_incident_ids)
        .select_related('school')
        .order_by('received_at')
    )
    fallback_arrival = list(active_nosla.filter(
        arrived_at__isnull=True,
        received_at__lt=now - timedelta(hours=sla_arrival_hours),
    ))
    fallback_resolve = list(active_nosla.filter(
        received_at__lt=now - timedelta(hours=sla_resolve_hours),
    ))

    def _fmt(dt):
        return timezone.localtime(dt).strftime('%m-%d %H:%M')

    def _overdue_min(target_dt):
        return max(0, int((now - timezone.localtime(target_dt)).total_seconds() / 60))

    arrival_overdue = [{
        'number':      r.incident.incident_number,
        'school':      r.incident.school.name,
        'target':      _fmt(r.arrival_target),
        'overdue_min': _overdue_min(r.arrival_target),
    } for r in sla_arrival_qs] + [{
        'number':      i.incident_number,
        'school':      i.school.name,
        'target':      _fmt(i.received_at + timedelta(hours=sla_arrival_hours)),
        'overdue_min': _overdue_min(i.received_at + timedelta(hours=sla_arrival_hours)),
    } for i in fallback_arrival]

    resolve_overdue = [{
        'number':      r.incident.incident_number,
        'school':      r.incident.school.name,
        'target':      _fmt(r.resolve_target),
        'overdue_min': _overdue_min(r.resolve_target),
    } for r in sla_resolve_qs] + [{
        'number':      i.incident_number,
        'school':      i.school.name,
        'target':      _fmt(i.received_at + timedelta(hours=sla_resolve_hours)),
        'overdue_min': _overdue_min(i.received_at + timedelta(hours=sla_resolve_hours)),
    } for i in fallback_resolve]

    # 초과 시간 기준 내림차순 정렬
    arrival_overdue.sort(key=lambda x: x['overdue_min'], reverse=True)
    resolve_overdue.sort(key=lambda x: x['overdue_min'], reverse=True)

    sla_warnings = {
        'arrival_overdue': arrival_overdue,
        'resolve_overdue': resolve_overdue,
        'arrival_count':   len(arrival_overdue),
        'resolve_count':   len(resolve_overdue),
    }

    return Response({
        'school_count':   school_count,
        'active_workers': active_workers,
        'online_count':   online_sessions.count(),
        'online_users':   list(online_users[:20]),
        'incidents':      inc_summary,
        'recent_incidents': recent_list,
        'sla_warnings':   sla_warnings,
        'timestamp':      now.strftime('%Y-%m-%d %H:%M:%S'),
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dashboard_zones(request):
    """대시보드 하단 3개 영역 데이터 (자재현황 / 인력배정 / 7일 추이)"""
    from apps.materials.models import Material, WarehouseInventory, MaterialOutbound
    from apps.incidents.models import Incident, IncidentAssignment
    from apps.statistics.models import StatisticsDaily
    from apps.accounts.models import User
    from datetime import timedelta

    now   = timezone.localtime(timezone.now())
    today = now.date()

    # ── 자재현황: 재고 부족 항목 (재고 < 최소재고) ────────────────────────
    low_stock = list(
        WarehouseInventory.objects.select_related('material', 'material__category')
        .filter(quantity__lt=F('material__min_stock'), material__min_stock__gt=0)
        .order_by('quantity')[:5]
        .values('material__name', 'material__unit', 'quantity', 'material__min_stock')
    )
    # 오늘 출고 건수
    today_outbound = MaterialOutbound.objects.filter(outbound_date=today).count()

    # ── 인력 배정현황: 오늘 배정된 기사별 현황 ───────────────────────────
    worker_stats = list(
        IncidentAssignment.objects.filter(assigned_at__date=today)
        .select_related('worker')
        .values('worker__name')
        .annotate(cnt=Count('id'))
        .order_by('-cnt')[:8]
    )
    # 미배정 장애 수
    unassigned = Incident.objects.filter(status='received').count()

    # ── 7일 장애 추이 ─────────────────────────────────────────────────────
    trend = []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        stat = StatisticsDaily.objects.filter(stat_date=d).first()
        trend.append({
            'date':  d.strftime('%m/%d'),
            'total': stat.total_incidents if stat else 0,
            'done':  stat.completed_incidents if stat else 0,
        })

    return Response({
        'materials': {
            'low_stock':      low_stock,
            'today_outbound': today_outbound,
        },
        'workers': {
            'assignments': worker_stats,
            'unassigned':  unassigned,
        },
        'trend': trend,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dashboard_workers_gis(request):
    """인력 GIS 데이터 (실시간 GPS 우선, 없으면 홈 위치)"""
    from apps.accounts.models import User
    from apps.gps.models import WorkerLocation
    from django.utils import timezone
    from datetime import timedelta

    cutoff = timezone.now() - timedelta(minutes=30)
    # 실시간 위치 맵
    realtime = {
        wl.worker_id: wl
        for wl in WorkerLocation.objects.select_related('worker').filter(updated_at__gte=cutoff)
    }

    workers = User.objects.filter(
        is_active=True, role__in=('worker', 'resident')
    ).select_related('support_center').order_by('name')

    result = []
    for w in workers:
        if w.id in realtime:
            wl = realtime[w.id]
            result.append({
                'id':          w.id,
                'name':        w.name,
                'role':        w.role,
                'lat':         float(wl.lat),
                'lng':         float(wl.lng),
                'phone':       w.phone or '',
                'location_type': 'realtime',
                'status':      wl.status,
                'device_type': wl.device_type,
                'updated_at':  wl.updated_at.isoformat(),
                'center_name': w.support_center.name if w.support_center else '',
            })
        elif w.home_lat and w.home_lng:
            result.append({
                'id':          w.id,
                'name':        w.name,
                'role':        w.role,
                'lat':         float(w.home_lat),
                'lng':         float(w.home_lng),
                'phone':       w.phone or '',
                'location_type': 'home',
                'status':      '',
                'device_type': '',
                'updated_at':  '',
                'center_name': w.support_center.name if w.support_center else '',
            })
    return Response(result)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dashboard_schedule(request):
    """대시보드 일정관리 위젯 데이터 (진행중 점검계획 + 이번주 예정 점검)"""
    from apps.progress.models import InspectionPlan, SchoolInspection
    from datetime import timedelta

    today = timezone.localdate()
    week_end = today + timedelta(days=7)

    # 진행중인 점검계획 (정기점검 최우선 정렬)
    TYPE_ORDER = ['regular', 'special', 'quarterly', 'project', 'survey', 'followup']
    raw_plans = list(
        InspectionPlan.objects.filter(status='active')
        .values('id', 'name', 'plan_type', 'start_date', 'end_date')
    )
    raw_plans.sort(key=lambda p: (TYPE_ORDER.index(p['plan_type']) if p['plan_type'] in TYPE_ORDER else 99, p['id']))
    active_plans = raw_plans[:5]
    for p in active_plans:
        total = SchoolInspection.objects.filter(plan_id=p['id']).count()
        done  = SchoolInspection.objects.filter(plan_id=p['id'], status='completed').count()
        p['total'] = total
        p['done']  = done
        p['pct']   = round(done / total * 100) if total else 0
        p['start_date'] = p['start_date'].strftime('%m/%d') if p['start_date'] else ''
        p['end_date']   = p['end_date'].strftime('%m/%d')   if p['end_date']   else ''

    # 각 계획별 오늘의 지원청별 점검 진척 (0 포함 전체 지원청)
    CENTER_ORDER = ['동부','서부','남부','북부','중부','강동송파','강서양천','강남서초','동작관악','성동광진','성북강북']

    for p in active_plans:
        today_plan_qs = SchoolInspection.objects.filter(
            plan_id=p['id'],
            scheduled_date=today,
        ).select_related('school__support_center')

        center_map = {}
        for si in today_plan_qs:
            name = si.school.support_center.name if si.school and si.school.support_center else '미분류'
            if name not in center_map:
                center_map[name] = {'total': 0, 'completed': 0}
            center_map[name]['total'] += 1
            if si.status == 'completed':
                center_map[name]['completed'] += 1

        # 11개 지원청 항상 포함 (없으면 0)
        today_centers = []
        for name in CENTER_ORDER:
            d = center_map.get(name, {'total': 0, 'completed': 0})
            today_centers.append({'name': name, 'total': d['total'], 'completed': d['completed']})
        for name, d in center_map.items():
            if name not in CENTER_ORDER:
                today_centers.append({'name': name, 'total': d['total'], 'completed': d['completed']})

        p['today_by_center'] = today_centers
        p['today_total']     = sum(d['total']     for d in center_map.values())
        p['today_completed'] = sum(d['completed'] for d in center_map.values())

    return Response({
        'active_plans': active_plans,
        'today_date':   today.strftime('%m/%d'),
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dashboard_incidents_stats(request):
    """지원청별 장애현황 통계 (일/주/월/분기/반기/년)"""
    from apps.incidents.models import Incident
    from datetime import timedelta

    period = request.GET.get('period', 'day')
    today  = timezone.localdate()

    if period == 'week':
        start = today - timedelta(days=today.weekday())
    elif period == 'month':
        start = today.replace(day=1)
    elif period == 'quarter':
        q = (today.month - 1) // 3
        start = today.replace(month=q * 3 + 1, day=1)
    elif period == 'half':
        start = today.replace(month=1 if today.month <= 6 else 7, day=1)
    elif period == 'year':
        start = today.replace(month=1, day=1)
    else:
        start = today

    CENTER_ORDER = ['동부','서부','남부','북부','중부','강동송파','강서양천','강남서초','동작관악','성동광진','성북강북']

    qs = Incident.objects.filter(received_at__date__gte=start).select_related('school__support_center')

    center_map = {}
    for inc in qs:
        name = inc.school.support_center.name if inc.school and inc.school.support_center else '기타'
        if name not in center_map:
            center_map[name] = {'total': 0, 'completed': 0}
        center_map[name]['total'] += 1
        if inc.status == 'completed':
            center_map[name]['completed'] += 1

    result = []
    for name in CENTER_ORDER:
        d = center_map.get(name, {'total': 0, 'completed': 0})
        t, c = d['total'], d['completed']
        result.append({'name': name, 'total': t, 'completed': c,
                        'pending': t - c, 'rate': round(c / t * 100) if t else 0})
    for name, d in center_map.items():
        if name not in CENTER_ORDER:
            t, c = d['total'], d['completed']
            result.append({'name': name, 'total': t, 'completed': c,
                            'pending': t - c, 'rate': round(c / t * 100) if t else 0})

    gt = sum(r['total'] for r in result)
    gc = sum(r['completed'] for r in result)

    if period == 'week':
        period_label = f'{start.strftime("%m/%d")}~{today.strftime("%m/%d")}'
    elif period == 'month':
        period_label = f'{today.strftime("%m")}월'
    elif period == 'quarter':
        q = (today.month - 1) // 3 + 1
        period_label = f'{today.year}년 {q}분기'
    elif period == 'half':
        h = '상반기' if today.month <= 6 else '하반기'
        period_label = f'{today.year}년 {h}'
    elif period == 'year':
        period_label = f'{today.year}년'
    else:
        period_label = today.strftime('%m/%d')

    return Response({
        'by_center': result,
        'grand': {'total': gt, 'completed': gc, 'pending': gt - gc,
                  'rate': round(gc / gt * 100) if gt else 0},
        'period': period,
        'period_label': period_label,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dashboard_attendance_stats(request):
    """지원청별 인력 근태현황 통계 (일/주/월/분기/반기/년)"""
    from apps.accounts.models import User
    from apps.workforce.models import AttendanceLog
    from datetime import timedelta

    period = request.GET.get('period', 'day')
    today  = timezone.localdate()

    if period == 'week':
        start = today - timedelta(days=today.weekday())
    elif period == 'month':
        start = today.replace(day=1)
    elif period == 'quarter':
        q = (today.month - 1) // 3
        start = today.replace(month=q * 3 + 1, day=1)
    elif period == 'half':
        start = today.replace(month=1 if today.month <= 6 else 7, day=1)
    elif period == 'year':
        start = today.replace(month=1, day=1)
    else:
        start = today

    CENTER_ORDER = ['동부','서부','남부','북부','중부','강동송파','강서양천','강남서초','동작관악','성동광진','성북강북','교육청']

    workers = list(User.objects.filter(role__in=('worker','resident'), is_active=True).select_related('support_center'))

    center_workers = {}
    for w in workers:
        name = w.support_center.name if w.support_center else '교육청'
        center_workers.setdefault(name, []).append(w.id)

    all_ids = [w.id for w in workers]

    # 기간 내 로그: worker_id → set of statuses / check_in 여부
    logs = AttendanceLog.objects.filter(
        worker_id__in=all_ids,
        work_date__gte=start,
        work_date__lte=today,
    ).values('worker_id', 'status', 'check_in_at')

    # worker_id → {checked_in: bool, leave: bool}
    worker_att = {}
    for log in logs:
        wid = log['worker_id']
        if wid not in worker_att:
            worker_att[wid] = {'checked_in': False, 'leave': False}
        if log['status'] == 'leave':
            worker_att[wid]['leave'] = True
        if log['check_in_at'] is not None and log['status'] != 'leave':
            worker_att[wid]['checked_in'] = True

    def _stats(wids):
        total      = len(wids)
        checked_in = sum(1 for wid in wids if worker_att.get(wid, {}).get('checked_in'))
        leave      = sum(1 for wid in wids if worker_att.get(wid, {}).get('leave'))
        return total, checked_in, leave

    result = []
    for name in CENTER_ORDER:
        t, ci, lv = _stats(center_workers.get(name, []))
        result.append({'name': name, 'total': t, 'checked_in': ci,
                        'leave': lv, 'rate': round(ci / t * 100) if t else 0})
    for name, wids in center_workers.items():
        if name not in CENTER_ORDER:
            t, ci, lv = _stats(wids)
            result.append({'name': name, 'total': t, 'checked_in': ci,
                            'leave': lv, 'rate': round(ci / t * 100) if t else 0})

    gt = sum(r['total'] for r in result)
    gi = sum(r['checked_in'] for r in result)
    gl = sum(r['leave'] for r in result)

    my_status = None
    if request.user.role in ('worker', 'resident'):
        my_log = AttendanceLog.objects.filter(worker=request.user, work_date=today).first()
        if my_log:
            if my_log.status == 'leave':
                my_status = 'leave'
            elif my_log.check_out_at:
                my_status = 'checked_out'
            elif my_log.check_in_at:
                my_status = 'checked_in'

    # 기간 레이블
    if period == 'week':
        period_label = f'{start.strftime("%m/%d")}~{today.strftime("%m/%d")}'
    elif period == 'month':
        period_label = f'{today.strftime("%m")}월'
    elif period == 'quarter':
        q = (today.month - 1) // 3 + 1
        period_label = f'{today.year}년 {q}분기'
    elif period == 'half':
        h = '상반기' if today.month <= 6 else '하반기'
        period_label = f'{today.year}년 {h}'
    elif period == 'year':
        period_label = f'{today.year}년'
    else:
        period_label = today.strftime('%m/%d')

    return Response({
        'by_center': result,
        'grand': {'total': gt, 'checked_in': gi, 'leave': gl,
                  'rate': round(gi / gt * 100) if gt else 0},
        'my_status': my_status,
        'period_label': period_label,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def dashboard_checkin(request):
    """출근 처리 (worker/resident 전용)"""
    from apps.workforce.models import AttendanceLog
    from apps.workforce.views import _get_device_type

    if request.user.role not in ('worker', 'resident'):
        return Response({'error': '현장기사 또는 상주인력만 출근 처리 가능합니다.'}, status=403)

    today  = timezone.localdate()
    now    = timezone.now()
    device = _get_device_type(request)

    lat = request.data.get('lat') or None
    lng = request.data.get('lng') or None

    log, created = AttendanceLog.objects.get_or_create(
        worker=request.user,
        work_date=today,
        defaults={
            'check_in_at': now, 'status': 'normal',
            'check_in_device': device,
            'check_in_lat': lat, 'check_in_lng': lng,
        },
    )
    if not created and not log.check_in_at:
        log.check_in_at     = now
        log.status          = 'normal'
        log.check_in_device = device
        log.check_in_lat    = lat
        log.check_in_lng    = lng
        log.save(update_fields=['check_in_at', 'status', 'check_in_device', 'check_in_lat', 'check_in_lng'])

    return Response({'success': True, 'checked_in_at': timezone.localtime(now).strftime('%H:%M')})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def dashboard_checkout(request):
    """퇴근 처리 (worker/resident 전용)"""
    from apps.workforce.models import AttendanceLog

    if request.user.role not in ('worker', 'resident'):
        return Response({'error': '현장기사 또는 상주인력만 퇴근 처리 가능합니다.'}, status=403)

    today = timezone.localdate()
    now   = timezone.now()

    log = AttendanceLog.objects.filter(worker=request.user, work_date=today).first()
    if not log or not log.check_in_at:
        return Response({'error': '출근 기록이 없습니다.'}, status=400)

    lat = request.data.get('lat') or None
    lng = request.data.get('lng') or None
    from apps.workforce.views import _get_device_type
    log.check_out_at     = now
    log.check_out_device = _get_device_type(request)
    log.check_out_lat    = lat
    log.check_out_lng    = lng
    log.save(update_fields=['check_out_at', 'check_out_device', 'check_out_lat', 'check_out_lng'])

    return Response({'success': True, 'checked_out_at': timezone.localtime(now).strftime('%H:%M')})


# ═══════════════════════════════════════════════════════
#  알림센터 API
# ═══════════════════════════════════════════════════════
from rest_framework import viewsets, status as drf_status
from rest_framework.decorators import action
from .models import Notification


class NotificationViewSet(viewsets.GenericViewSet):
    """앱 내 알림 API"""
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)

    # GET /api/dashboard/notifications/
    def list(self, request):
        qs = self.get_queryset()[:50]
        data = [_noti_dict(n) for n in qs]
        return Response(data)

    # GET /api/dashboard/notifications/unread_count/
    @action(detail=False, methods=['get'])
    def unread_count(self, request):
        cnt = self.get_queryset().filter(is_read=False).count()
        return Response({'count': cnt})

    # POST /api/dashboard/notifications/{id}/read/
    @action(detail=True, methods=['post'])
    def read(self, request, pk=None):
        n = self.get_queryset().filter(pk=pk).first()
        if n and not n.is_read:
            n.is_read = True
            n.read_at = timezone.now()
            n.save(update_fields=['is_read', 'read_at'])
        return Response({'ok': True})

    # POST /api/dashboard/notifications/read_all/
    @action(detail=False, methods=['post'])
    def read_all(self, request):
        self.get_queryset().filter(is_read=False).update(
            is_read=True, read_at=timezone.now()
        )
        return Response({'ok': True})

    # DELETE /api/dashboard/notifications/clear/
    @action(detail=False, methods=['delete'])
    def clear(self, request):
        self.get_queryset().filter(is_read=True).delete()
        return Response({'ok': True})


def _noti_dict(n):
    ICONS = {
        'incident': 'bi-exclamation-triangle-fill',
        'sla':      'bi-shield-exclamation',
        'wbs':      'bi-diagram-3-fill',
        'inspection':'bi-clipboard2-check-fill',
        'report':   'bi-file-earmark-text-fill',
        'system':   'bi-bell-fill',
    }
    COLORS = {
        'info': 'text-primary', 'warning': 'text-warning',
        'danger': 'text-danger', 'success': 'text-success',
    }
    return {
        'id':         n.id,
        'ntype':      n.ntype,
        'level':      n.level,
        'title':      n.title,
        'message':    n.message,
        'link':       n.link,
        'is_read':    n.is_read,
        'created_at': n.created_at.strftime('%m.%d %H:%M'),
        'icon':       ICONS.get(n.ntype, 'bi-bell-fill'),
        'color':      COLORS.get(n.level, 'text-primary'),
    }
