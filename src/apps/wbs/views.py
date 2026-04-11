"""
WBS 앱 뷰
"""
from datetime import date
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, F, ExpressionWrapper, FloatField
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models import WBSItem
from .serializers import WBSItemSerializer, WBSSummarySerializer


@login_required
def wbs_view(request):
    return render(request, 'wbs/index.html')


class WBSItemViewSet(viewsets.ModelViewSet):
    serializer_class   = WBSItemSerializer
    permission_classes = [IsAuthenticated]
    pagination_class   = None

    def get_queryset(self):
        qs = WBSItem.objects.select_related(
            'parent', 'assignee', 'linked_template', 'linked_inspection'
        )
        project_id = self.request.query_params.get('project')
        if project_id:
            qs = qs.filter(project_id=project_id)
        phase = self.request.query_params.get('phase')
        if phase:
            qs = qs.filter(phase=phase)
        depth = self.request.query_params.get('depth')
        if depth:
            qs = qs.filter(depth=depth)
        return qs

    @action(detail=False, methods=['get'], url_path='gantt')
    def gantt(self, request):
        """Gantt 차트용 포맷 반환"""
        project_id = request.query_params.get('project')
        if not project_id:
            return Response({'error': 'project 파라미터 필요'}, status=400)

        items = WBSItem.objects.filter(project_id=project_id).order_by('seq')
        data = []
        for item in items:
            data.append({
                'id':            item.id,
                'code':          item.code,
                'text':          item.name,
                'depth':         item.depth,
                'parent':        item.parent_id,
                'start_date':    item.planned_start.strftime('%Y-%m-%d') if item.planned_start else None,
                'end_date':      item.planned_end.strftime('%Y-%m-%d')   if item.planned_end   else None,
                'actual_start':  item.actual_start.strftime('%Y-%m-%d') if item.actual_start else None,
                'actual_end':    item.actual_end.strftime('%Y-%m-%d')   if item.actual_end   else None,
                'progress':      item.progress / 100,
                'weight':        float(item.weight),
                'is_milestone':  item.is_milestone,
                'open':          item.depth <= 2,
            })
        return Response(data)

    @action(detail=False, methods=['get'], url_path='summary')
    def summary(self, request):
        """페이즈별 계획진척률 / 실적진척률 / 공정준수율 집계"""
        project_id = request.query_params.get('project')
        if not project_id:
            return Response({'error': 'project 파라미터 필요'}, status=400)

        today = date.today()
        phase_labels = {'plan': '계획', 'execute': '수행', 'close': '종료'}
        result = []

        for phase_key, phase_label in phase_labels.items():
            items = WBSItem.objects.filter(
                project_id=project_id, phase=phase_key
            ).exclude(progress_source='children')

            total_weight = sum(float(i.weight) for i in items) or 1

            # 계획진척률: 오늘 기준으로 완료되어야 할 항목의 가중 합
            planned = 0.0
            actual  = 0.0
            for i in items:
                w = float(i.weight)
                # 계획진척: 계획 종료일이 오늘 이전이면 100%, 아직 안 됐으면 0%
                if i.planned_end and i.planned_end <= today:
                    planned += w * 100
                elif i.planned_start and i.planned_start <= today and i.planned_end:
                    elapsed = (today - i.planned_start).days
                    total   = (i.planned_end - i.planned_start).days or 1
                    planned += w * min(elapsed / total * 100, 100)

                actual += w * i.progress

            planned_pct = round(planned / total_weight, 1)
            actual_pct  = round(actual  / total_weight, 1)
            compliance  = round(actual_pct / planned_pct * 100, 1) if planned_pct else 0

            result.append({
                'phase':            phase_key,
                'phase_display':    phase_label,
                'planned_progress': planned_pct,
                'actual_progress':  actual_pct,
                'compliance_rate':  compliance,
                'total_weight':     total_weight,
            })

        # 전체 합산
        all_items = WBSItem.objects.filter(
            project_id=project_id
        ).exclude(progress_source='children')
        tw = sum(float(i.weight) for i in all_items) or 1
        planned_all = 0.0
        actual_all  = 0.0
        for i in all_items:
            w = float(i.weight)
            if i.planned_end and i.planned_end <= today:
                planned_all += w * 100
            elif i.planned_start and i.planned_start <= today and i.planned_end:
                elapsed = (today - i.planned_start).days
                total   = (i.planned_end - i.planned_start).days or 1
                planned_all += w * min(elapsed / total * 100, 100)
            actual_all += w * i.progress

        planned_all_pct = round(planned_all / tw, 1)
        actual_all_pct  = round(actual_all  / tw, 1)
        result.append({
            'phase':            'total',
            'phase_display':    '전체',
            'planned_progress': planned_all_pct,
            'actual_progress':  actual_all_pct,
            'compliance_rate':  round(actual_all_pct / planned_all_pct * 100, 1) if planned_all_pct else 0,
            'total_weight':     tw,
        })

        return Response(result)

    @action(detail=True, methods=['patch'], url_path='progress')
    def update_progress(self, request, pk=None):
        """진척률 수동 업데이트 (manual 소스 항목만)"""
        item = self.get_object()
        if item.progress_source != 'manual':
            return Response(
                {'error': f'이 항목은 {item.get_progress_source_display()} 소스로 자동 관리됩니다.'},
                status=400
            )
        val = request.data.get('progress')
        try:
            progress_int = int(val)
        except (TypeError, ValueError):
            return Response({'error': '0~100 사이 값 필요'}, status=400)
        if not (0 <= progress_int <= 100):
            return Response({'error': '0~100 사이 값 필요'}, status=400)
        item.progress = progress_int
        fields = ['progress', 'updated_at']
        for f in ['this_week_plan', 'this_week_actual', 'next_week_plan', 'notes',
                  'actual_start', 'actual_end']:
            if f in request.data:
                setattr(item, f, request.data[f])
                fields.append(f)
        item.save(update_fields=fields)

        # 부모 버블업
        from apps.wbs.signals import _bubble_up
        _bubble_up(item)

        return Response(WBSItemSerializer(item).data)
