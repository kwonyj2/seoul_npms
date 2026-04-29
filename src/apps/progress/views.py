from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Count, Q

from .models import InspectionPlan, SchoolInspection, Holiday, WorkerArea
from .serializers import (
    InspectionPlanListSerializer, InspectionPlanDetailSerializer,
    InspectionPlanCreateSerializer, InspectionPlanUpdateSerializer,
    SchoolInspectionSerializer,
    HolidaySerializer, WorkerAreaSerializer, InspectionUploadLogSerializer,
)
from core.pagination import StandardPagination


@login_required
def progress_view(request):
    return render(request, 'progress/index.html')


# ──────────────────────────────────────────────────
# 휴일 관리
# ──────────────────────────────────────────────────
class HolidayViewSet(viewsets.ModelViewSet):
    serializer_class   = HolidaySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = Holiday.objects.all()
        year = self.request.query_params.get('year')
        if year:
            from django.db.models import Q
            qs = qs.filter(
                Q(is_recurring=True) |
                Q(specific_date__year=year)
            )
        active = self.request.query_params.get('active')
        if active is not None:
            qs = qs.filter(is_active=(active.lower() == 'true'))
        return qs


# ──────────────────────────────────────────────────
# 인력-담당구역 관리
# ──────────────────────────────────────────────────
class WorkerAreaViewSet(viewsets.ModelViewSet):
    serializer_class   = WorkerAreaSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = WorkerArea.objects.select_related('worker', 'support_center')
        worker = self.request.query_params.get('worker')
        center = self.request.query_params.get('support_center')
        if worker: qs = qs.filter(worker_id=worker)
        if center: qs = qs.filter(support_center_id=center)
        return qs

    @action(detail=False, methods=['post'])
    def create_from_users(self, request):
        """User.support_center 기반 WorkerArea 자동 생성"""
        from .services import create_worker_areas_from_users
        result = create_worker_areas_from_users()
        return Response(result)


# ──────────────────────────────────────────────────
# 점검 계획
# ──────────────────────────────────────────────────
class InspectionPlanViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    pagination_class   = StandardPagination

    def get_serializer_class(self):
        if self.action == 'create':
            return InspectionPlanCreateSerializer
        if self.action in ('update', 'partial_update'):
            return InspectionPlanUpdateSerializer
        if self.action == 'retrieve':
            return InspectionPlanDetailSerializer
        return InspectionPlanListSerializer

    def get_queryset(self):
        qs = InspectionPlan.objects.prefetch_related('school_inspections').select_related('created_by')
        year = self.request.query_params.get('year')
        pt   = self.request.query_params.get('plan_type')
        st   = self.request.query_params.get('status')
        if year: qs = qs.filter(year=year)
        if pt:   qs = qs.filter(plan_type=pt)
        if st:   qs = qs.filter(status=st)
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=False, methods=['get'])
    def current_quarter(self, request):
        """오늘 날짜 기준 현재 진행 중인 차수 반환"""
        from django.utils import timezone
        today = timezone.localdate()
        plan = InspectionPlan.objects.filter(
            start_date__lte=today, end_date__gte=today
        ).order_by('quarter').first()
        if plan:
            return Response({'quarter': plan.quarter})
        # 진행 중인 기간 없으면 가장 가까운 미래 차수
        plan = InspectionPlan.objects.filter(start_date__gt=today).order_by('start_date').first()
        if plan:
            return Response({'quarter': plan.quarter})
        return Response({'quarter': 1})

    @action(detail=True, methods=['post'])
    def add_schools(self, request, pk=None):
        """학교 목록 추가"""
        plan = self.get_object()
        school_ids = request.data.get('school_ids', [])
        if not school_ids:
            return Response({'error': 'school_ids 필요'}, status=status.HTTP_400_BAD_REQUEST)
        from apps.schools.models import School
        schools = School.objects.filter(id__in=school_ids, is_active=True)
        created = 0
        for s in schools:
            _, is_new = SchoolInspection.objects.get_or_create(plan=plan, school=s)
            if is_new:
                created += 1
        return Response({'added': created})

    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        """계획 활성화"""
        plan = self.get_object()
        plan.status = 'active'
        plan.save(update_fields=['status'])
        return Response(InspectionPlanListSerializer(plan).data)

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        """계획 완료 처리"""
        plan = self.get_object()
        plan.status = 'completed'
        plan.save(update_fields=['status'])
        return Response(InspectionPlanListSerializer(plan).data)

    @action(detail=True, methods=['get'])
    def stats(self, request, pk=None):
        """계획별 통계"""
        plan = self.get_object()
        qs = plan.school_inspections.select_related('school__support_center', 'assigned_worker')

        by_center = {}
        for si in qs:
            c = si.school.support_center.name if si.school.support_center else '미분류'
            if c not in by_center:
                by_center[c] = {'total': 0, 'completed': 0, 'scheduled': 0, 'pending': 0}
            by_center[c]['total'] += 1
            by_center[c][si.status if si.status in ('completed', 'scheduled', 'pending') else 'pending'] += 1

        by_worker = {}
        for si in qs.filter(assigned_worker__isnull=False):
            w = si.assigned_worker.name
            if w not in by_worker:
                by_worker[w] = {'total': 0, 'completed': 0}
            by_worker[w]['total'] += 1
            if si.status == 'completed':
                by_worker[w]['completed'] += 1

        return Response({
            'plan_id':      plan.id,
            'plan_name':    plan.name,
            'total':        plan.total,
            'completed':    plan.completed_count,
            'progress_pct': plan.progress_pct,
            'by_status': {
                'pending':   qs.filter(status='pending').count(),
                'scheduled': qs.filter(status='scheduled').count(),
                'completed': qs.filter(status='completed').count(),
                'skipped':   qs.filter(status='skipped').count(),
            },
            'by_center': [{'name': k, **v} for k, v in by_center.items()],
            'by_worker': [{'name': k, **v} for k, v in by_worker.items()],
        })

    @action(detail=True, methods=['post'])
    def auto_assign(self, request, pk=None):
        """업무일 자동배정 (근접거리 최적화, 계획 기간·인력 기준 자동 계산)"""
        plan = self.get_object()
        force_reassign = bool(request.data.get('force_reassign', False))
        from .services import auto_assign
        result = auto_assign(plan.id, force_reassign=force_reassign)
        return Response(result)

    @action(detail=True, methods=['post'])
    def reset_assignments(self, request, pk=None):
        """배정 초기화 (scheduled → pending)"""
        plan = self.get_object()
        from .services import reset_assignments
        result = reset_assignments(plan.id)
        return Response(result)

    @action(detail=True, methods=['get'])
    def csv_download(self, request, pk=None):
        """현재 필터 조건으로 CSV 다운로드"""
        import urllib.parse
        from datetime import date as _date
        plan = self.get_object()
        qs = plan.school_inspections.select_related(
            'school__support_center', 'school__school_type', 'assigned_worker'
        )
        # 필터 적용
        st      = request.query_params.get('status')
        center  = request.query_params.get('center')
        worker  = request.query_params.get('worker')
        sname   = request.query_params.get('school_name')
        sdate   = request.query_params.get('scheduled_date')
        tab     = request.query_params.get('tab', 'school')
        if st:
            if ',' in st:
                qs = qs.filter(status__in=st.split(','))
            else:
                qs = qs.filter(status=st)
        if center:  qs = qs.filter(school__support_center_id=center)
        if worker:  qs = qs.filter(assigned_worker_id=worker)
        if sname:   qs = qs.filter(school__name__icontains=sname)
        if sdate:   qs = qs.filter(scheduled_date=sdate)
        ordering = request.query_params.get('ordering', 'school__support_center__name,school__name')
        qs = qs.order_by(*ordering.split(','))

        from .services import generate_csv_download
        csv_bytes = generate_csv_download(qs)
        today = _date.today().strftime('%Y%m%d')
        filename = urllib.parse.quote(f'점검현황_{plan.name}_{tab}_{today}.csv')
        resp = HttpResponse(csv_bytes, content_type='text/csv; charset=utf-8-sig')
        resp['Content-Disposition'] = f'attachment; filename*=UTF-8\'\'{filename}'
        return resp

    @action(detail=True, methods=['post'])
    def replace_worker(self, request, pk=None):
        """기사 교체 (교체 전 기사의 미완료 업무를 신규 기사에게 이관)"""
        plan = self.get_object()
        old_worker_id = request.data.get('old_worker_id')
        new_worker_id = request.data.get('new_worker_id')
        from_date     = request.data.get('from_date')  # YYYY-MM-DD or None
        if not old_worker_id or not new_worker_id:
            return Response({'error': 'old_worker_id, new_worker_id 필요'},
                            status=status.HTTP_400_BAD_REQUEST)
        from .services import replace_worker
        result = replace_worker(plan.id, old_worker_id, new_worker_id, from_date)
        return Response(result)

    @action(detail=False, methods=['get'])
    def download_template(self, request):
        """Excel 업로드 템플릿 다운로드"""
        plan_type = request.query_params.get('plan_type', 'special')
        from .services import generate_template_excel
        wb_bytes = generate_template_excel(plan_type)
        resp = HttpResponse(
            wb_bytes,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        resp['Content-Disposition'] = f'attachment; filename="inspection_template_{plan_type}.xlsx"'
        return resp

    @action(detail=True, methods=['post'])
    def upload_schools(self, request, pk=None):
        """Excel/CSV 업로드 → 학교 매칭 미리보기 (DB 변경 없음)"""
        plan = self.get_object()
        file_obj = request.FILES.get('file')
        if not file_obj:
            return Response({'error': '파일을 첨부하세요'}, status=status.HTTP_400_BAD_REQUEST)
        from .services import process_upload
        result = process_upload(file_obj)
        # plan_id를 미리보기 결과에 포함
        result['plan_id'] = plan.id
        return Response(result)

    @action(detail=True, methods=['post'])
    def confirm_upload(self, request, pk=None):
        """업로드 미리보기 확인 → DB 저장"""
        plan = self.get_object()
        rows      = request.data.get('rows', [])
        file_name = request.data.get('file_name', '')
        if not rows:
            return Response({'error': 'rows 데이터 없음'}, status=status.HTTP_400_BAD_REQUEST)
        from .services import confirm_upload
        result = confirm_upload(plan.id, rows, request.user, file_name)
        return Response(result)


# ──────────────────────────────────────────────────
# 학교별 점검 항목
# ──────────────────────────────────────────────────
class SchoolInspectionViewSet(viewsets.ModelViewSet):
    serializer_class   = SchoolInspectionSerializer
    permission_classes = [permissions.IsAuthenticated]

    ORDERING_WHITELIST = {
        'scheduled_date', '-scheduled_date',
        'completed_date', '-completed_date',
        'school__name', '-school__name',
        'school__support_center__name', '-school__support_center__name',
        'assigned_worker__name', '-assigned_worker__name',
        'priority', '-priority', 'status', '-status',
    }

    def get_queryset(self):
        qs = SchoolInspection.objects.select_related(
            'plan', 'school', 'school__support_center', 'school__school_type',
            'assigned_worker', 'report', 'replaced_from', 'work_schedule'
        )
        plan_id     = self.request.query_params.get('plan_id')
        st          = self.request.query_params.get('status')
        worker      = self.request.query_params.get('worker')
        school      = self.request.query_params.get('school')
        school_name = self.request.query_params.get('school_name')
        center      = self.request.query_params.get('center')
        school_type = self.request.query_params.get('school_type')
        date        = self.request.query_params.get('scheduled_date')
        ordering    = self.request.query_params.get('ordering')

        if plan_id:     qs = qs.filter(plan_id=plan_id)
        if st:
            if ',' in st:
                qs = qs.filter(status__in=st.split(','))
            else:
                qs = qs.filter(status=st)
        if worker:      qs = qs.filter(assigned_worker_id=worker)
        if school:      qs = qs.filter(school_id=school)
        if school_name: qs = qs.filter(school__name__icontains=school_name)
        if center:      qs = qs.filter(school__support_center_id=center)
        if school_type: qs = qs.filter(school__school_type_id=school_type)
        if date:        qs = qs.filter(scheduled_date=date)
        if ordering:
            fields = [f.strip() for f in ordering.split(',') if f.strip() in self.ORDERING_WHITELIST]
            if fields:
                qs = qs.order_by(*fields)
        return qs

    @action(detail=True, methods=['post'])
    def mark_complete(self, request, pk=None):
        """점검 완료 처리"""
        si = self.get_object()
        from django.utils import timezone
        si.status = 'completed'
        si.completed_date = request.data.get('completed_date') or timezone.localdate()
        si.notes = request.data.get('notes', si.notes)
        si.save(update_fields=['status', 'completed_date', 'notes', 'updated_at'])
        return Response(SchoolInspectionSerializer(si).data)
