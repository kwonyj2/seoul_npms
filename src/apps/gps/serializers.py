from rest_framework import serializers
from django.utils import timezone
from .models import GpsLog, WorkerLocation, RouteHistory, GeoFence, GeoFenceEvent


def _get_device_type(request):
    """User-Agent로 단말 유형 판별"""
    if not request:
        return 'unknown'
    ua = request.META.get('HTTP_USER_AGENT', '').lower()
    if any(k in ua for k in ['android', 'iphone', 'ipad', 'ipod', 'blackberry', 'windows phone', 'mobile']):
        return 'mobile'
    return 'pc'


class GpsLogSerializer(serializers.ModelSerializer):
    worker_name = serializers.CharField(source='worker.name', read_only=True)

    class Meta:
        model = GpsLog
        fields = ['id', 'worker', 'worker_name', 'lat', 'lng', 'accuracy',
                  'speed', 'heading', 'altitude', 'device_id', 'device_type', 'is_moving', 'logged_at']
        read_only_fields = ['id', 'device_type']

    def create(self, validated_data):
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            validated_data.setdefault('worker', request.user)
        if 'logged_at' not in validated_data:
            validated_data['logged_at'] = timezone.now()
        validated_data['device_type'] = _get_device_type(request)
        log = super().create(validated_data)
        # WorkerLocation 갱신 (단말 유형 포함)
        WorkerLocation.objects.update_or_create(
            worker=log.worker,
            defaults={
                'lat': log.lat, 'lng': log.lng,
                'status': 'moving' if log.is_moving else 'idle',
                'device_type': log.device_type,
            }
        )
        return log


class WorkerLocationSerializer(serializers.ModelSerializer):
    worker_name  = serializers.CharField(source='worker.name', read_only=True)
    worker_role  = serializers.CharField(source='worker.role', read_only=True)
    center_name  = serializers.CharField(source='worker.support_center.name', read_only=True)
    center_id    = serializers.IntegerField(source='worker.support_center_id', read_only=True)
    phone        = serializers.CharField(source='worker.phone', read_only=True)

    class Meta:
        model = WorkerLocation
        fields = ['worker', 'worker_name', 'worker_role', 'center_name', 'center_id',
                  'phone', 'lat', 'lng', 'status', 'device_type', 'updated_at']


class RouteHistorySerializer(serializers.ModelSerializer):
    worker_name = serializers.CharField(source='worker.name', read_only=True)
    incident_number = serializers.CharField(source='incident.incident_number', read_only=True)

    class Meta:
        model = RouteHistory
        fields = ['id', 'worker', 'worker_name', 'incident', 'incident_number',
                  'started_at', 'ended_at', 'start_lat', 'start_lng',
                  'end_lat', 'end_lng', 'distance_km', 'route_points']
        read_only_fields = ['id']


class GeoFenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = GeoFence
        fields = ['id', 'name', 'fence_type', 'center_lat', 'center_lng',
                  'radius_m', 'is_active', 'created_at']
        read_only_fields = ['id', 'created_at']


class GeoFenceEventSerializer(serializers.ModelSerializer):
    worker_name = serializers.CharField(source='worker.name', read_only=True)
    fence_name  = serializers.CharField(source='fence.name', read_only=True)

    class Meta:
        model = GeoFenceEvent
        fields = ['id', 'worker', 'worker_name', 'fence', 'fence_name',
                  'event_type', 'lat', 'lng', 'occurred_at']
        read_only_fields = ['id', 'occurred_at']
