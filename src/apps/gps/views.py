from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from django.db.models import Q
from datetime import timedelta

from .models import GpsLog, WorkerLocation, RouteHistory, GeoFence, GeoFenceEvent


@login_required
def gps_map_view(request):
    return render(request, 'gps/map.html')
from .serializers import (
    GpsLogSerializer, WorkerLocationSerializer,
    RouteHistorySerializer, GeoFenceSerializer, GeoFenceEventSerializer
)
from core.permissions.roles import IsAdmin, IsSuperAdmin
from core.pagination import StandardPagination


class GpsLogViewSet(viewsets.ModelViewSet):
    """GPS 로그 - 현장기사 위치 수집"""
    serializer_class = GpsLogSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardPagination
    http_method_names = ['get', 'post', 'head', 'options']

    def get_queryset(self):
        user = self.request.user
        qs = GpsLog.objects.select_related('worker')
        if user.role == 'worker':
            qs = qs.filter(worker=user)
        worker_id = self.request.query_params.get('worker_id')
        if worker_id:
            qs = qs.filter(worker_id=worker_id)
        date = self.request.query_params.get('date')
        if date:
            qs = qs.filter(logged_at__date=date)
        # 기본: 최근 24시간
        since = self.request.query_params.get('since')
        if since:
            qs = qs.filter(logged_at__gte=since)
        elif not date and not worker_id:
            qs = qs.filter(logged_at__gte=timezone.now() - timedelta(hours=24))
        return qs

    def perform_create(self, serializer):
        serializer.save(worker=self.request.user)

    @action(detail=False, methods=['get'])
    def my_today(self, request):
        """내 오늘 GPS 로그"""
        logs = GpsLog.objects.filter(
            worker=request.user,
            logged_at__date=timezone.localdate()
        ).order_by('logged_at')
        data = GpsLogSerializer(logs, many=True).data
        return Response({'count': len(data), 'logs': data})


class WorkerLocationViewSet(viewsets.ReadOnlyModelViewSet):
    """인력 현재 위치 (관리자용 실시간 지도)"""
    serializer_class = WorkerLocationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = WorkerLocation.objects.select_related('worker').filter(
            worker__role='worker', worker__is_active=True
        )
        # 최근 30분 이내 갱신된 인력만
        cutoff = timezone.now() - timedelta(minutes=30)
        qs = qs.filter(updated_at__gte=cutoff)
        return qs

    @action(detail=False, methods=['get'])
    def active(self, request):
        """현재 활동 중인 인력 위치 목록 (대시보드 지도용)"""
        locations = self.get_queryset()
        data = WorkerLocationSerializer(locations, many=True).data
        return Response(data)


class RouteHistoryViewSet(viewsets.ModelViewSet):
    """이동 경로 기록"""
    serializer_class = RouteHistorySerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardPagination

    def get_queryset(self):
        user = self.request.user
        qs = RouteHistory.objects.select_related('worker', 'incident')
        if user.role == 'worker':
            qs = qs.filter(worker=user)
        worker_id = self.request.query_params.get('worker_id')
        if worker_id:
            qs = qs.filter(worker_id=worker_id)
        incident_id = self.request.query_params.get('incident_id')
        if incident_id:
            qs = qs.filter(incident_id=incident_id)
        date = self.request.query_params.get('date')
        if date:
            qs = qs.filter(started_at__date=date)
        return qs

    @action(detail=True, methods=['post'])
    def end_route(self, request, pk=None):
        """경로 종료 (도착 처리)"""
        route = self.get_object()
        end_lat = request.data.get('end_lat')
        end_lng = request.data.get('end_lng')
        if not end_lat or not end_lng:
            return Response({'error': '도착 좌표가 필요합니다.'}, status=status.HTTP_400_BAD_REQUEST)
        route.ended_at = timezone.now()
        route.end_lat = end_lat
        route.end_lng = end_lng
        route.save(update_fields=['ended_at', 'end_lat', 'end_lng'])
        return Response(RouteHistorySerializer(route).data)

    @action(detail=True, methods=['post'])
    def add_point(self, request, pk=None):
        """경로에 좌표 추가"""
        route = self.get_object()
        lat = request.data.get('lat')
        lng = request.data.get('lng')
        if not lat or not lng:
            return Response({'error': '좌표가 필요합니다.'}, status=status.HTTP_400_BAD_REQUEST)
        points = route.route_points or []
        points.append({'lat': float(lat), 'lng': float(lng), 'time': timezone.now().isoformat()})
        route.route_points = points
        route.save(update_fields=['route_points'])
        return Response({'count': len(points)})


class GeoFenceViewSet(viewsets.ModelViewSet):
    """지오펜스 관리"""
    serializer_class = GeoFenceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = GeoFence.objects.all()
        fence_type = self.request.query_params.get('fence_type')
        if fence_type:
            qs = qs.filter(fence_type=fence_type)
        active_only = self.request.query_params.get('active')
        if active_only == '1':
            qs = qs.filter(is_active=True)
        return qs

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdmin()]
        return [IsAuthenticated()]


class GeoFenceEventViewSet(viewsets.ReadOnlyModelViewSet):
    """지오펜스 이벤트 조회"""
    serializer_class = GeoFenceEventSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardPagination

    def get_queryset(self):
        qs = GeoFenceEvent.objects.select_related('worker', 'fence')
        worker_id = self.request.query_params.get('worker_id')
        if worker_id:
            qs = qs.filter(worker_id=worker_id)
        fence_id = self.request.query_params.get('fence_id')
        if fence_id:
            qs = qs.filter(fence_id=fence_id)
        since = self.request.query_params.get('since')
        if since:
            qs = qs.filter(occurred_at__gte=since)
        return qs
