from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Avg, Count

from .models import AiModel, AiJob, WorkerAssignmentPrediction, IncidentPattern
from .serializers import (
    AiModelSerializer, AiJobSerializer,
    WorkerAssignmentPredictionSerializer, IncidentPatternSerializer
)
from . import services as ai_services
from core.permissions.roles import IsAdmin, IsSuperAdmin
from core.pagination import StandardPagination


class AiModelViewSet(viewsets.ModelViewSet):
    """AI 모델 관리"""
    serializer_class = AiModelSerializer
    permission_classes = [IsAuthenticated]
    queryset = AiModel.objects.all()

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsSuperAdmin()]
        return [IsAuthenticated()]

    @action(detail=False, methods=['get'])
    def health(self, request):
        """AI 서버 헬스체크"""
        return Response(ai_services.ai_server_health())


class AiJobViewSet(viewsets.ReadOnlyModelViewSet):
    """AI 작업 이력"""
    serializer_class = AiJobSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardPagination

    def get_queryset(self):
        qs = AiJob.objects.select_related('ai_model')
        job_type = self.request.query_params.get('job_type')
        if job_type:
            qs = qs.filter(job_type=job_type)
        st = self.request.query_params.get('status')
        if st:
            qs = qs.filter(status=st)
        return qs

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """AI 작업 요약"""
        from django.utils import timezone
        from datetime import timedelta
        since = timezone.now() - timedelta(days=7)
        qs = AiJob.objects.filter(created_at__gte=since)
        by_status = qs.values('status').annotate(cnt=Count('id'))
        by_type   = qs.values('job_type').annotate(cnt=Count('id'))
        return Response({
            'total_7d':   qs.count(),
            'by_status':  {s['status']: s['cnt'] for s in by_status},
            'by_type':    {t['job_type']: t['cnt'] for t in by_type},
            'success_rate': round(
                qs.filter(status='success').count() / qs.count() * 100, 1
            ) if qs.count() else 0,
        })


class WorkerAssignmentPredictionViewSet(viewsets.ReadOnlyModelViewSet):
    """인력 배정 예측 결과"""
    serializer_class = WorkerAssignmentPredictionSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardPagination

    def get_queryset(self):
        qs = WorkerAssignmentPrediction.objects.select_related(
            'incident', 'recommended_worker'
        )
        incident_id = self.request.query_params.get('incident_id')
        if incident_id:
            qs = qs.filter(incident_id=incident_id)
        is_accepted = self.request.query_params.get('accepted')
        if is_accepted == '1':
            qs = qs.filter(is_accepted=True)
        elif is_accepted == '0':
            qs = qs.filter(is_accepted=False)
        return qs

    @action(detail=False, methods=['post'])
    def predict(self, request):
        """인력 배정 AI 예측 호출
        payload: {incident_id, workers: [{worker_id, worker_name, lat, lng, current_workload}]}
        """
        try:
            result = ai_services._ai_post(
                '/predict/worker_assignment', request.data
            )
            return Response(result)
        except Exception as exc:
            return Response({'error': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

    @action(detail=True, methods=['post'])
    def accept(self, request, pk=None):
        """예측 채택"""
        prediction = self.get_object()
        prediction.is_accepted = True
        prediction.save(update_fields=['is_accepted'])
        return Response({'message': '채택 완료'})

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """예측 거부"""
        prediction = self.get_object()
        prediction.is_accepted = False
        prediction.save(update_fields=['is_accepted'])
        return Response({'message': '거부 완료'})


class IncidentPatternViewSet(viewsets.ReadOnlyModelViewSet):
    """장애 패턴 분석 결과"""
    serializer_class = IncidentPatternSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardPagination

    def get_queryset(self):
        qs = IncidentPattern.objects.select_related('school', 'category')
        school_id = self.request.query_params.get('school_id')
        if school_id:
            qs = qs.filter(school_id=school_id)
        pattern_type = self.request.query_params.get('pattern_type')
        if pattern_type:
            qs = qs.filter(pattern_type__icontains=pattern_type)
        return qs

    @action(detail=False, methods=['post'])
    def analyze(self, request):
        """장애 패턴 AI 분석 호출
        payload: {incidents: [...], top_n: 5}
        """
        try:
            result = ai_services._ai_post(
                '/analyze/incident_pattern', request.data
            )
            return Response(result)
        except Exception as exc:
            return Response({'error': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)


class MaterialForecastViewSet(viewsets.ViewSet):
    """자재 수요 예측 AI 호출"""
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['post'])
    def forecast(self, request):
        """자재 수요 예측 호출
        payload: {material_id, material_name, usage_history, forecast_periods, window}
        """
        try:
            result = ai_services._ai_post(
                '/predict/material_forecast', request.data
            )
            return Response(result)
        except Exception as exc:
            return Response({'error': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

    @action(detail=False, methods=['post'])
    def batch(self, request):
        """자재 수요 일괄 예측"""
        try:
            result = ai_services._ai_post(
                '/predict/material_forecast/batch', request.data
            )
            return Response(result)
        except Exception as exc:
            return Response({'error': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
