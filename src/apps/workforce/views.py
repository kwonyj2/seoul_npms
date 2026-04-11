import csv
import logging
from django.shortcuts import render
from django.http import HttpResponse, JsonResponse
from django.contrib.auth.decorators import login_required

logger = logging.getLogger(__name__)
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from .models import WorkScheduleType, WorkSchedule, AttendanceLog, AttendanceException, TaskAssignment
from .serializers import WorkScheduleTypeSerializer, WorkScheduleSerializer, AttendanceLogSerializer

CENTER_ORDER = ['동부','서부','남부','북부','중부',
                '강동송파','강서양천','강남서초','동작관악','성동광진','성북강북']


def _get_device_type(request):
    """User-Agent로 단말 유형 판별 (pc / mobile / unknown)"""
    if not request:
        return 'unknown'
    ua = request.META.get('HTTP_USER_AGENT', '').lower()
    if any(k in ua for k in ['android', 'iphone', 'ipad', 'ipod', 'blackberry', 'windows phone', 'mobile']):
        return 'mobile'
    return 'pc'


@login_required
def schedule_view(request):
    return render(request, 'workforce/schedule.html')


@login_required
def center_worker_tree(request):
    """지원청-인력 트리 데이터 (좌측 패널용)"""
    from apps.schools.models import SupportCenter
    from apps.accounts.models import User

    centers_qs = SupportCenter.objects.all()
    center_map = {c.name: {'id': c.id, 'name': c.name, 'workers': []} for c in centers_qs}

    workers = User.objects.filter(
        role__in=['worker', 'resident'],
        support_center__isnull=False,
    ).select_related('support_center').order_by('name')

    for w in workers:
        cname = w.support_center.name
        if cname in center_map:
            center_map[cname]['workers'].append({
                'id': w.id, 'name': w.name,
                'role': w.role, 'role_label': w.get_role_display(),
            })

    ordered = [center_map[c] for c in CENTER_ORDER if c in center_map]
    for c in center_map:
        if c not in CENTER_ORDER:
            ordered.append(center_map[c])

    return JsonResponse({'centers': ordered})


@login_required
def today_schedule_kpi(request):
    """오늘 KPI 수치 (상단 카드용)"""
    from apps.accounts.models import User
    today = timezone.localdate()

    total_workers = User.objects.filter(
        role__in=['worker', 'resident'], support_center__isnull=False
    ).count()
    today_checkin = AttendanceLog.objects.filter(
        work_date=today, check_in_at__isnull=False
    ).count()

    qs_today = WorkSchedule.objects.filter(start_dt__date=today)
    return JsonResponse({
        'total_workers':  total_workers,
        'today_checkin':  today_checkin,
        'today_regular':  qs_today.filter(schedule_type__code='regular_check').count(),
        'today_special':  qs_today.filter(schedule_type__code='special_check').count(),
        'today_incident': qs_today.filter(schedule_type__code='incident').count(),
        'today_other':    qs_today.exclude(
            schedule_type__code__in=['regular_check', 'special_check', 'incident']
        ).count(),
    })


@login_required
def attendance_view(request):
    return render(request, 'workforce/attendance.html')


class WorkScheduleTypeViewSet(viewsets.ModelViewSet):
    queryset = WorkScheduleType.objects.filter(is_active=True)
    serializer_class = WorkScheduleTypeSerializer
    permission_classes = [permissions.IsAuthenticated]


def _sync_inspection(ws):
    """WorkSchedule 변경 → 연결된 SchoolInspection 동기화"""
    try:
        from apps.progress.models import SchoolInspection
        sis = SchoolInspection.objects.filter(work_schedule=ws)
        if not sis.exists():
            return
        STATUS_MAP = {
            'completed':   ('completed', True),
            'cancelled':   ('skipped',   False),
            'in_progress': ('scheduled', False),
            'planned':     ('scheduled', False),
        }
        si_status, set_done = STATUS_MAP.get(ws.status, ('scheduled', False))
        for si in sis:
            si.assigned_worker  = ws.worker
            si.scheduled_date   = ws.start_dt.date()
            si.status           = si_status
            if set_done and not si.completed_date:
                si.completed_date = ws.end_dt.date()
            if ws.school:
                si.school = ws.school
            si.save(update_fields=[
                'assigned_worker', 'scheduled_date', 'status',
                'completed_date', 'school', 'updated_at'
            ])
    except Exception as e:
        logger.warning('점검계획 동기화 실패 schedule=%s: %s', ws.pk, e)


class WorkScheduleViewSet(viewsets.ModelViewSet):
    queryset = WorkSchedule.objects.select_related('worker', 'schedule_type', 'school', 'incident').order_by('-start_dt')
    serializer_class = WorkScheduleSerializer
    permission_classes = [permissions.IsAuthenticated]

    def _check_write_permission(self, schedule):
        """본인 일정 또는 관리자만 수정/삭제 가능"""
        user = self.request.user
        if user.role not in ('superadmin', 'admin') and schedule.worker != user:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('본인 일정만 수정할 수 있습니다.')

    def perform_update(self, serializer):
        instance = serializer.save()
        _sync_inspection(instance)

    def perform_destroy(self, instance):
        """삭제 시 SchoolInspection 연결 해제 후 삭제"""
        try:
            from apps.progress.models import SchoolInspection
            SchoolInspection.objects.filter(work_schedule=instance).update(
                work_schedule=None, status='pending',
                scheduled_date=None, assigned_worker=None,
            )
        except Exception as e:
            logger.warning('일정 삭제 시 점검계획 연결 해제 실패 schedule=%s: %s', instance.pk, e)
        instance.delete()

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        worker = params.get('worker')
        date_from = params.get('date_from')
        date_to   = params.get('date_to')
        stype     = params.get('type')
        if worker:
            qs = qs.filter(worker_id=worker)
        if date_from:
            qs = qs.filter(start_dt__date__gte=date_from)
        if date_to:
            qs = qs.filter(start_dt__date__lte=date_to)
        if stype:
            qs = qs.filter(schedule_type__code=stype)
        # 현장기사/재직자는 자신 일정만, superadmin/admin은 전체
        if self.request.user.role not in ('superadmin', 'admin'):
            qs = qs.filter(worker=self.request.user)
        return qs

    @action(detail=False, methods=['get'])
    def calendar(self, request):
        """FullCalendar 형식 이벤트 반환"""
        qs = self.get_queryset()

        # 상태별 스타일 오버라이드
        STATUS_STYLE = {
            'completed':   {'bg': '#e2e8f0', 'border': '#94a3b8', 'text': '#64748b'},
            'cancelled':   {'bg': '#fee2e2', 'border': '#fca5a5', 'text': '#b0b0b0'},
            'in_progress': {'bg': None,      'border': None,       'text': '#ffffff'},
            'planned':     {'bg': None,      'border': None,       'text': '#ffffff'},
        }

        events = []
        for s in qs:
            style = STATUS_STYLE.get(s.status, STATUS_STYLE['planned'])
            events.append({
                'id':              s.id,
                'title':           f'[{s.schedule_type.name}] {s.title}',
                'start':           s.start_dt.isoformat(),
                'end':             s.end_dt.isoformat(),
                'backgroundColor': style['bg'] or s.schedule_type.color,
                'borderColor':     style['border'] or s.schedule_type.color,
                'textColor':       style['text'],
                'extendedProps': {
                    'worker':       s.worker.name,
                    'worker_id':    s.worker.id,
                    'school':       s.school.name if s.school else '',
                    'status':       s.status,
                    'status_label': s.get_status_display(),
                    'type_code':    s.schedule_type.code,
                    'type_name':    s.schedule_type.name,
                    'type_color':   s.schedule_type.color,
                }
            })
        return Response(events)

    @action(detail=True, methods=['patch'])
    def update_status(self, request, pk=None):
        """일정 상태 변경 (본인 일정 또는 관리자)"""
        schedule = self.get_object()
        user = request.user

        # 권한 체크: 관리자 또는 본인 일정만
        if user.role not in ('superadmin', 'admin') and schedule.worker != user:
            return Response({'error': '권한이 없습니다.'}, status=status.HTTP_403_FORBIDDEN)

        new_status = request.data.get('status')
        valid = [c[0] for c in WorkSchedule.STATUS_CHOICES]
        if new_status not in valid:
            return Response({'error': f'유효하지 않은 상태: {new_status}'}, status=status.HTTP_400_BAD_REQUEST)

        schedule.status = new_status
        schedule.save(update_fields=['status', 'updated_at'])
        _sync_inspection(schedule)
        return Response({
            'id':           schedule.id,
            'status':       schedule.status,
            'status_label': schedule.get_status_display(),
        })

    @action(detail=False, methods=['get'])
    def today(self, request):
        """오늘 일정"""
        today = timezone.localdate()
        qs = self.get_queryset().filter(start_dt__date=today)
        return Response(WorkScheduleSerializer(qs, many=True).data)


class AttendanceLogViewSet(viewsets.ModelViewSet):
    queryset = AttendanceLog.objects.select_related('worker').order_by('-work_date')
    serializer_class = AttendanceLogSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        worker    = params.get('worker')
        date_from = params.get('date_from')
        date_to   = params.get('date_to')
        att_status= params.get('status')

        if self.request.user.role == 'worker':
            qs = qs.filter(worker=self.request.user)
        elif worker:
            qs = qs.filter(worker_id=worker)

        if date_from:
            qs = qs.filter(work_date__gte=date_from)
        if date_to:
            qs = qs.filter(work_date__lte=date_to)
        if att_status:
            qs = qs.filter(status=att_status)
        return qs

    @action(detail=False, methods=['get'])
    def csv_download(self, request):
        response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
        response['Content-Disposition'] = 'attachment; filename="attendance.csv"'
        writer = csv.writer(response)
        writer.writerow(['근무일', '인력명', '출근시각', '퇴근시각', '근무시간(h)', '상태', '출근위도', '출근경도', '퇴근위도', '퇴근경도', '비고'])
        for r in self.get_queryset():
            writer.writerow([
                r.work_date,
                r.worker.name,
                timezone.localtime(r.check_in_at).strftime('%Y-%m-%d %H:%M') if r.check_in_at else '',
                timezone.localtime(r.check_out_at).strftime('%Y-%m-%d %H:%M') if r.check_out_at else '',
                r.get_work_hours() or '',
                r.get_status_display(),
                r.check_in_lat or '', r.check_in_lng or '',
                r.check_out_lat or '', r.check_out_lng or '',
                r.note,
            ])
        return response

    @action(detail=False, methods=['post'])
    def check_in(self, request):
        """GPS 출근"""
        today  = timezone.localdate()
        device = _get_device_type(request)
        log, created = AttendanceLog.objects.get_or_create(
            worker=request.user, work_date=today,
            defaults={
                'check_in_at':     timezone.now(),
                'check_in_lat':    request.data.get('lat'),
                'check_in_lng':    request.data.get('lng'),
                'check_in_device': device,
            }
        )
        if not created and not log.check_in_at:
            log.check_in_at     = timezone.now()
            log.check_in_lat    = request.data.get('lat')
            log.check_in_lng    = request.data.get('lng')
            log.check_in_device = device
            log.save(update_fields=['check_in_at', 'check_in_lat', 'check_in_lng', 'check_in_device'])
        return Response(AttendanceLogSerializer(log).data)

    @action(detail=False, methods=['post'])
    def check_out(self, request):
        """GPS 퇴근"""
        today  = timezone.localdate()
        device = _get_device_type(request)
        try:
            log = AttendanceLog.objects.get(worker=request.user, work_date=today)
            log.check_out_at     = timezone.now()
            log.check_out_lat    = request.data.get('lat')
            log.check_out_lng    = request.data.get('lng')
            log.check_out_device = device
            log.save(update_fields=['check_out_at', 'check_out_lat', 'check_out_lng', 'check_out_device'])
            return Response(AttendanceLogSerializer(log).data)
        except AttendanceLog.DoesNotExist:
            return Response({'error': '출근 기록이 없습니다.'}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'])
    def self_report(self, request):
        """개인 사유 등록 (연차/병가/휴가/반차 등)"""
        work_date  = request.data.get('work_date')
        att_status = request.data.get('status')
        note       = request.data.get('note', '')
        if not work_date or not att_status:
            return Response({'error': 'work_date, status 필수'}, status=status.HTTP_400_BAD_REQUEST)
        valid = [c[0] for c in AttendanceLog.STATUS_CHOICES]
        if att_status not in valid:
            return Response({'error': f'유효하지 않은 상태: {att_status}'}, status=status.HTTP_400_BAD_REQUEST)
        log, _ = AttendanceLog.objects.get_or_create(
            worker=request.user, work_date=work_date,
            defaults={'status': att_status, 'note': note},
        )
        if not _:
            log.status = att_status
            log.note   = note
            log.save(update_fields=['status', 'note'])
        return Response(AttendanceLogSerializer(log).data)

    @action(detail=False, methods=['post'])
    def admin_upsert(self, request):
        """관리자: 특정 인력/날짜 근태 등록·수정"""
        if request.user.role not in ('superadmin', 'admin'):
            return Response({'error': '관리자만 가능합니다.'}, status=status.HTTP_403_FORBIDDEN)
        worker_id   = request.data.get('worker')
        work_date   = request.data.get('work_date')
        att_status  = request.data.get('status')
        note        = request.data.get('note', '')
        check_in_at = request.data.get('check_in_at')
        check_out_at= request.data.get('check_out_at')
        if not worker_id or not work_date:
            return Response({'error': 'worker, work_date 필수'}, status=status.HTTP_400_BAD_REQUEST)
        log, created = AttendanceLog.objects.get_or_create(
            worker_id=worker_id, work_date=work_date,
            defaults={'status': att_status or 'normal', 'note': note},
        )
        if not created:
            update_fields = ['note']
            log.note = note
            if att_status:
                log.status = att_status
                update_fields.append('status')
            if check_in_at is not None:
                log.check_in_at = check_in_at or None
                update_fields.append('check_in_at')
            if check_out_at is not None:
                log.check_out_at = check_out_at or None
                update_fields.append('check_out_at')
            log.save(update_fields=update_fields)
        return Response(AttendanceLogSerializer(log).data)

    @action(detail=False, methods=['delete'])
    def admin_delete(self, request):
        """관리자: 특정 인력/날짜 근태 삭제"""
        if request.user.role not in ('superadmin', 'admin'):
            return Response({'error': '관리자만 가능합니다.'}, status=status.HTTP_403_FORBIDDEN)
        worker_id = request.query_params.get('worker')
        work_date = request.query_params.get('work_date')
        if not worker_id or not work_date:
            return Response({'error': 'worker, work_date 필수'}, status=status.HTTP_400_BAD_REQUEST)
        deleted, _ = AttendanceLog.objects.filter(worker_id=worker_id, work_date=work_date).delete()
        return Response({'deleted': deleted})

    @action(detail=False, methods=['get'])
    def monthly_grid(self, request):
        """월별 그리드 (관리자: 인력×일별 근태 매트릭스)"""
        import calendar
        from datetime import date
        from apps.accounts.models import User
        year  = int(request.query_params.get('year',  timezone.localdate().year))
        month = int(request.query_params.get('month', timezone.localdate().month))
        center_id = request.query_params.get('center')
        days_in_month = calendar.monthrange(year, month)[1]
        date_from = date(year, month, 1)
        date_to   = date(year, month, days_in_month)

        workers_qs = User.objects.filter(
            role__in=['worker', 'resident'], support_center__isnull=False
        ).select_related('support_center').order_by('name')
        if center_id:
            workers_qs = workers_qs.filter(support_center_id=center_id)

        logs = AttendanceLog.objects.filter(
            work_date__range=(date_from, date_to), worker__in=workers_qs
        )
        log_map = {}
        for log in logs:
            log_map.setdefault(log.worker_id, {})[log.work_date.day] = log

        def center_order_key(w):
            cname = w.support_center.name if w.support_center else ''
            try:
                return (CENTER_ORDER.index(cname), w.name)
            except ValueError:
                return (len(CENTER_ORDER), w.name)

        result = []
        for w in sorted(workers_qs, key=center_order_key):
            wlogs = log_map.get(w.id, {})
            daily = {}
            for d in range(1, days_in_month + 1):
                lg = wlogs.get(d)
                if lg:
                    daily[d] = {
                        'id':        lg.id,
                        'status':    lg.status,
                        'check_in':  timezone.localtime(lg.check_in_at).strftime('%H:%M') if lg.check_in_at else None,
                        'check_out': timezone.localtime(lg.check_out_at).strftime('%H:%M') if lg.check_out_at else None,
                        'note':      lg.note,
                    }
                else:
                    daily[d] = None
            result.append({
                'worker_id':   w.id,
                'worker_name': w.name,
                'center_name': w.support_center.name,
                'center_id':   w.support_center_id,
                'daily':       daily,
            })
        return Response({'year': year, 'month': month, 'days': days_in_month, 'workers': result})

    @action(detail=False, methods=['get'])
    def period_summary(self, request):
        """기간별 집계 (월/분기/반기/연)"""
        import calendar
        from datetime import date
        from apps.accounts.models import User
        year        = int(request.query_params.get('year', timezone.localdate().year))
        period_type = request.query_params.get('period_type', 'month')  # month|quarter|half|year
        period_num  = int(request.query_params.get('period_num', 1))
        center_id   = request.query_params.get('center')

        if period_type == 'month':
            date_from = date(year, period_num, 1)
            date_to   = date(year, period_num, calendar.monthrange(year, period_num)[1])
        elif period_type == 'quarter':
            m0 = (period_num - 1) * 3 + 1
            m1 = period_num * 3
            date_from = date(year, m0, 1)
            date_to   = date(year, m1, calendar.monthrange(year, m1)[1])
        elif period_type == 'half':
            m0, m1 = (1, 6) if period_num == 1 else (7, 12)
            date_from = date(year, m0, 1)
            date_to   = date(year, m1, calendar.monthrange(year, m1)[1])
        else:  # year
            date_from = date(year, 1, 1)
            date_to   = date(year, 12, 31)

        workers_qs = User.objects.filter(
            role__in=['worker', 'resident'], support_center__isnull=False
        ).select_related('support_center').order_by('name')
        if center_id:
            workers_qs = workers_qs.filter(support_center_id=center_id)

        from collections import defaultdict
        logs = AttendanceLog.objects.filter(work_date__range=(date_from, date_to), worker__in=workers_qs)
        w_counts = defaultdict(lambda: defaultdict(int))
        w_hours  = defaultdict(list)
        for lg in logs:
            w_counts[lg.worker_id][lg.status] += 1
            h = lg.get_work_hours()
            if h:
                w_hours[lg.worker_id].append(h)

        def center_order_key(w):
            cname = w.support_center.name if w.support_center else ''
            try:
                return (CENTER_ORDER.index(cname), w.name)
            except ValueError:
                return (len(CENTER_ORDER), w.name)

        result = []
        for w in sorted(workers_qs, key=center_order_key):
            counts = dict(w_counts.get(w.id, {}))
            hrs    = w_hours.get(w.id, [])
            result.append({
                'worker_id':   w.id,
                'worker_name': w.name,
                'center_name': w.support_center.name,
                'center_id':   w.support_center_id,
                'counts':      counts,
                'total_days':  sum(counts.values()),
                'avg_hours':   round(sum(hrs) / len(hrs), 1) if hrs else None,
            })
        return Response({
            'period_type': period_type, 'year': year, 'period_num': period_num,
            'date_from': str(date_from), 'date_to': str(date_to),
            'workers': result,
        })


# ═══════════════════════════════════════════════════════════════
#  인력 관리 뷰 (현장기사 전용)
# ═══════════════════════════════════════════════════════════════

@login_required
def worker_list_view(request):
    return render(request, 'workforce/workers.html')


@login_required
def worker_only_tree(request):
    """현장기사(role=worker)만 포함한 지원청-인력 트리"""
    from apps.schools.models import SupportCenter
    from apps.accounts.models import User

    centers_qs = SupportCenter.objects.all()
    center_map = {c.name: {'id': c.id, 'name': c.name, 'workers': []} for c in centers_qs}

    workers = User.objects.filter(
        role='worker',
        support_center__isnull=False,
    ).select_related('support_center').order_by('name')

    for w in workers:
        cname = w.support_center.name
        if cname in center_map:
            has_img = bool(w.profile_image)
            center_map[cname]['workers'].append({
                'id':         w.id,
                'name':       w.name,
                'phone':      w.phone,
                'is_active':  w.is_active,
                'has_photo':  has_img,
                'photo_url':  w.profile_image.url if has_img else '',
            })

    ordered = [center_map[c] for c in CENTER_ORDER if c in center_map]
    for c in center_map:
        if c not in CENTER_ORDER:
            ordered.append(center_map[c])

    return JsonResponse({'centers': ordered})


@login_required
def worker_profile_api(request, worker_id):
    """현장기사 신상·프로필 조회(GET) / 저장(POST)"""
    import json
    from apps.accounts.models import User
    from .models import WorkerProfile

    try:
        worker = User.objects.select_related('support_center', 'worker_profile').get(
            pk=worker_id, role='worker'
        )
    except User.DoesNotExist:
        return JsonResponse({'error': '인력을 찾을 수 없습니다.'}, status=404)

    if request.method == 'GET':
        try:
            prof = worker.worker_profile
        except WorkerProfile.DoesNotExist:
            prof = None
        return JsonResponse({
            'id':             worker.id,
            'username':       worker.username,
            'name':           worker.name,
            'phone':          worker.phone,
            'email':          worker.email,
            'center_name':    worker.support_center.name if worker.support_center else '',
            'home_address':   worker.home_address,
            'is_active':      worker.is_active,
            'created_at':     timezone.localtime(worker.created_at).strftime('%Y-%m-%d'),
            'photo_url':      worker.profile_image.url if worker.profile_image else '',
            'birth_date':     str(prof.birth_date) if prof and prof.birth_date else '',
            'join_date':      str(prof.join_date)  if prof and prof.join_date  else '',
            'career_summary': prof.career_summary  if prof else '',
            'bio':            prof.bio             if prof else '',
            'notes':          prof.notes           if prof else '',
        })

    if request.method == 'POST':
        # 프로필 텍스트 저장
        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            body = request.POST.dict()

        prof, _ = WorkerProfile.objects.get_or_create(worker=worker)
        for field in ('birth_date', 'join_date', 'career_summary', 'bio', 'notes'):
            val = body.get(field)
            if val is not None:
                setattr(prof, field, val or None if field in ('birth_date', 'join_date') else val)
        prof.save()
        return JsonResponse({'ok': True})

    return JsonResponse({'error': 'Method not allowed'}, status=405)


def _worker_name_stem(worker):
    """
    파일명 앞부분 생성: '{지원청}_{이름}' 또는 '{지원청}_{이름}{순번}'
    - 같은 지원청 내 동명이인 존재 시 생년월일 오름차순(나이 많은 순) 1부터 번호 부여
    - 생년월일 미입력자는 가장 젊은 것으로 간주(마지막)
    """
    from apps.accounts.models import User

    center_name = worker.support_center.name if worker.support_center else '미배정'
    peers = list(
        User.objects.filter(
            role='worker',
            support_center=worker.support_center,
            name=worker.name,
        ).prefetch_related('worker_profile')
    )

    def _birth(w):
        try:
            bd = w.worker_profile.birth_date
            return (0, bd) if bd else (1, None)
        except Exception:
            return (1, None)

    peers.sort(key=_birth)

    if len(peers) <= 1:
        return f"{center_name}_{worker.name}"

    rank = next((i + 1 for i, w in enumerate(peers) if w.pk == worker.pk), 1)
    return f"{center_name}_{worker.name}{rank}"


def _unique_doc_path(cat_dir, stem, cat_label, ext):
    """
    '{stem}_{cat_label}.{ext}' 가 이미 존재하면 '_2', '_3' … 을 붙여 중복 회피
    """
    import os
    base = f"{stem}_{cat_label}.{ext}"
    if not os.path.exists(os.path.join(cat_dir, base)):
        return base
    n = 2
    while True:
        candidate = f"{stem}_{cat_label}_{n}.{ext}"
        if not os.path.exists(os.path.join(cat_dir, candidate)):
            return candidate
        n += 1


@login_required
def worker_photo_api(request, worker_id):
    """증명사진 업로드(POST) / 삭제(DELETE)
    저장 경로: MEDIA_ROOT/data/인력관리/증명사진/{지원청}_{이름[순번]}_증명사진.{ext}
    """
    import os
    from django.conf import settings
    from apps.accounts.models import User

    try:
        worker = User.objects.select_related('support_center').get(pk=worker_id, role='worker')
    except User.DoesNotExist:
        return JsonResponse({'error': '인력을 찾을 수 없습니다.'}, status=404)

    photo_dir = os.path.join(settings.MEDIA_ROOT, 'data', '인력관리', '증명사진')

    if request.method == 'POST':
        photo = request.FILES.get('photo')
        if not photo:
            return JsonResponse({'error': '파일을 선택하세요.'}, status=400)
        ext = photo.name.rsplit('.', 1)[-1].lower()
        if ext not in ('jpg', 'jpeg', 'png', 'gif', 'webp'):
            return JsonResponse({'error': '이미지 파일만 업로드 가능합니다.'}, status=400)

        stem      = _worker_name_stem(worker)
        safe_name = f"{stem}_증명사진.{ext}"
        rel_path  = os.path.join('data', '인력관리', '증명사진', safe_name)
        abs_path  = os.path.join(photo_dir, safe_name)

        os.makedirs(photo_dir, exist_ok=True)
        # 기존 증명사진 삭제 (다른 확장자 포함)
        if worker.profile_image:
            old_abs = os.path.join(settings.MEDIA_ROOT, str(worker.profile_image))
            if os.path.isfile(old_abs):
                os.remove(old_abs)

        with open(abs_path, 'wb') as fh:
            for chunk in photo.chunks():
                fh.write(chunk)

        worker.profile_image = rel_path
        worker.save(update_fields=['profile_image'])
        return JsonResponse({'ok': True, 'photo_url': f"{settings.MEDIA_URL}{rel_path}"})

    if request.method == 'DELETE':
        if worker.profile_image:
            old_abs = os.path.join(settings.MEDIA_ROOT, str(worker.profile_image))
            if os.path.isfile(old_abs):
                os.remove(old_abs)
            worker.profile_image = None
            worker.save(update_fields=['profile_image'])
        return JsonResponse({'ok': True})

    return JsonResponse({'error': 'Method not allowed'}, status=405)


# NAS 인력관리 서류 카테고리
WORKER_DOC_CATEGORIES = [
    {'key': '성범죄경력조회',          'label': '성범죄 경력조회 및 행정정보공동이용 동의서'},
    {'key': '보안서약서',              'label': '보안서약서'},
    {'key': '경력증명서',              'label': '경력증명서'},
    {'key': '자격증',                  'label': '자격증'},
    {'key': '기타',                    'label': '기타 서류'},
]
WORKER_DOC_ALLOWED_EXTS = ('jpg', 'jpeg', 'png', 'gif', 'webp', 'pdf')


@login_required
def worker_docs_api(request, worker_id):
    """인력 서류 파일 목록 조회(GET) / 업로드(POST) / 삭제(DELETE)
    저장 경로: MEDIA_ROOT/data/인력관리/{카테고리키}/{지원청}_{이름[순번]}_{카테고리라벨}.{ext}
    """
    import os
    from django.conf import settings
    from apps.accounts.models import User

    try:
        worker = User.objects.select_related('support_center').get(pk=worker_id, role='worker')
    except User.DoesNotExist:
        return JsonResponse({'error': '인력을 찾을 수 없습니다.'}, status=404)

    nas_root = os.path.join(settings.MEDIA_ROOT, 'data', '인력관리')
    nas_url  = f"{settings.MEDIA_URL}data/인력관리/"

    if request.method == 'GET':
        stem   = _worker_name_stem(worker)
        result = []
        for cat in WORKER_DOC_CATEGORIES:
            cat_dir = os.path.join(nas_root, cat['key'])
            cat_url = nas_url + cat['key'] + '/'
            files   = []
            if os.path.isdir(cat_dir):
                prefix = stem + '_'
                for fname in sorted(os.listdir(cat_dir)):
                    if not fname.startswith(prefix):
                        continue
                    ext = fname.rsplit('.', 1)[-1].lower() if '.' in fname else ''
                    if ext in WORKER_DOC_ALLOWED_EXTS:
                        files.append({
                            'name':     fname,
                            'url':      cat_url + fname,
                            'is_image': ext in ('jpg', 'jpeg', 'png', 'gif', 'webp'),
                            'is_pdf':   ext == 'pdf',
                        })
            result.append({'key': cat['key'], 'label': cat['label'], 'files': files})
        return JsonResponse({'categories': result})

    if request.method == 'POST':
        cat_key = request.POST.get('category', '기타')
        cat_obj = next((c for c in WORKER_DOC_CATEGORIES if c['key'] == cat_key), None)
        if not cat_obj:
            cat_key = '기타'
            cat_obj = next(c for c in WORKER_DOC_CATEGORIES if c['key'] == '기타')

        upload = request.FILES.get('file')
        if not upload:
            return JsonResponse({'error': '파일을 선택하세요.'}, status=400)
        ext = upload.name.rsplit('.', 1)[-1].lower() if '.' in upload.name else ''
        if ext not in WORKER_DOC_ALLOWED_EXTS:
            return JsonResponse({'error': '이미지(jpg/png/gif/webp) 또는 PDF만 업로드 가능합니다.'}, status=400)

        cat_dir   = os.path.join(nas_root, cat_key)
        os.makedirs(cat_dir, exist_ok=True)

        stem      = _worker_name_stem(worker)
        safe_name = _unique_doc_path(cat_dir, stem, cat_obj['label'], ext)
        dest      = os.path.join(cat_dir, safe_name)

        with open(dest, 'wb') as fh:
            for chunk in upload.chunks():
                fh.write(chunk)

        cat_url = nas_url + cat_key + '/'
        return JsonResponse({
            'ok':       True,
            'name':     safe_name,
            'url':      cat_url + safe_name,
            'is_image': ext in ('jpg', 'jpeg', 'png', 'gif', 'webp'),
            'is_pdf':   ext == 'pdf',
        })

    if request.method == 'DELETE':
        import json as _json
        try:
            body    = _json.loads(request.body)
            cat_key = body.get('category', '')
            fname   = body.get('filename', '')
        except Exception:
            return JsonResponse({'error': '잘못된 요청입니다.'}, status=400)
        if not fname or not cat_key:
            return JsonResponse({'error': 'category, filename 필수'}, status=400)
        safe_name = os.path.basename(fname)
        target    = os.path.join(nas_root, cat_key, safe_name)
        if os.path.isfile(target):
            os.remove(target)
        return JsonResponse({'ok': True})

    return JsonResponse({'error': 'Method not allowed'}, status=405)
