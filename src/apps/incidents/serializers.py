from rest_framework import serializers
from django.utils import timezone
from .models import (
    IncidentCategory, IncidentSubcategory, Incident,
    IncidentAssignment, IncidentStatusHistory, IncidentComment,
    IncidentPhoto, IncidentSLA, SLARule, WorkOrder
)


class IncidentCategorySerializer(serializers.ModelSerializer):
    subcategories = serializers.SerializerMethodField()

    class Meta:
        model = IncidentCategory
        fields = ['id', 'code', 'name', 'order', 'subcategories']

    def get_subcategories(self, obj):
        return IncidentSubcategorySerializer(obj.subcategories.filter(is_active=True), many=True).data


class IncidentSubcategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = IncidentSubcategory
        fields = ['id', 'name', 'is_other', 'order']


class IncidentListSerializer(serializers.ModelSerializer):
    school_name        = serializers.CharField(source='school.name', read_only=True)
    center_name        = serializers.CharField(source='school.support_center.name', read_only=True)
    category_name      = serializers.CharField(source='category.name', read_only=True)
    subcategory_name   = serializers.CharField(source='subcategory.name', read_only=True)
    status_display     = serializers.CharField(source='get_status_display', read_only=True)
    priority_display   = serializers.CharField(source='get_priority_display', read_only=True)
    elapsed_minutes    = serializers.SerializerMethodField()
    assigned_worker    = serializers.SerializerMethodField()

    class Meta:
        model = Incident
        fields = ['id', 'incident_number', 'school_name', 'center_name',
                  'category_name', 'subcategory_name', 'status', 'status_display',
                  'priority', 'priority_display', 'received_at', 'completed_at',
                  'elapsed_minutes', 'assigned_worker', 'sla_arrival_ok', 'sla_resolve_ok']

    def get_elapsed_minutes(self, obj):
        return obj.get_elapsed_minutes()

    def get_assigned_worker(self, obj):
        assign = obj.assignments.filter(is_accepted=True).first() \
                 or obj.assignments.first()
        return assign.worker.name if assign else None


class IncidentDetailSerializer(serializers.ModelSerializer):
    school_name           = serializers.CharField(source='school.name', read_only=True)
    school_address        = serializers.CharField(source='school.address', read_only=True)
    school_lat            = serializers.FloatField(source='school.lat', read_only=True)
    school_lng            = serializers.FloatField(source='school.lng', read_only=True)
    center_name           = serializers.CharField(source='school.support_center.name', read_only=True)
    category_name         = serializers.CharField(source='category.name', read_only=True)
    subcategory_name      = serializers.CharField(source='subcategory.name', read_only=True)
    status_display        = serializers.CharField(source='get_status_display', read_only=True)
    priority_display      = serializers.CharField(source='get_priority_display', read_only=True)
    received_by_name      = serializers.CharField(source='received_by.name', read_only=True)
    assigned_worker_name  = serializers.SerializerMethodField()
    elapsed_minutes       = serializers.SerializerMethodField()
    location_building_name = serializers.CharField(source='location_building.name', read_only=True, default=None)
    location_floor_name    = serializers.CharField(source='location_floor.floor_name', read_only=True, default=None)
    location_room_name     = serializers.CharField(source='location_room.name', read_only=True, default=None)

    class Meta:
        model = Incident
        fields = '__all__'

    def get_assigned_worker_name(self, obj):
        assign = obj.assignments.filter(is_accepted=True).first() \
                 or obj.assignments.first()
        return assign.worker.name if assign else None

    def get_elapsed_minutes(self, obj):
        return obj.get_elapsed_minutes()


class IncidentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Incident
        fields = ['school', 'category', 'subcategory', 'other_detail', 'priority',
                  'contact_method', 'requester_name', 'requester_phone',
                  'requester_position', 'description', 'fault_type', 'is_human_error',
                  'location_building', 'location_floor', 'location_room', 'location_detail']

    def create(self, validated_data):
        from django.conf import settings
        from core.sla_utils import add_business_hours

        request = self.context.get('request')
        validated_data['received_by'] = request.user if request else None
        validated_data['incident_number'] = Incident.generate_number()

        # ── 재발 장애 감지 ──────────────────────────────────────────────
        school   = validated_data.get('school')
        category = validated_data.get('category')
        if school and category:
            cutoff_24h = timezone.now() - timezone.timedelta(hours=24)
            original = (
                Incident.objects
                .filter(
                    school=school,
                    category=category,
                    status='completed',
                    completed_at__gte=cutoff_24h,
                )
                .order_by('-completed_at')
                .first()
            )
            if original:
                validated_data['is_recurrence']     = True
                validated_data['original_incident'] = original

        incident = super().create(validated_data)

        # ── SLA 목표시각: 업무시간 기준 계산 ──────────────────────────
        sla_arrival = getattr(settings, 'SLA_ARRIVAL_HOURS', 2)
        sla_resolve = getattr(settings, 'SLA_RESOLVE_HOURS', 8)

        # 재발 장애는 원장애 received_at 부터 SLA 시계 시작
        sla_base = (
            incident.original_incident.received_at
            if incident.is_recurrence and incident.original_incident
            else incident.received_at
        )
        IncidentSLA.objects.create(
            incident=incident,
            arrival_target=add_business_hours(sla_base, sla_arrival),
            resolve_target=add_business_hours(sla_base, sla_resolve),
        )
        return incident


class IncidentUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Incident
        fields = ['status', 'priority', 'resolution', 'resolution_type',
                  'arrived_at', 'started_at', 'completed_at', 'description',
                  'fault_type', 'is_human_error']

    def update(self, instance, validated_data):
        old_status = instance.status
        old_arrived_at = instance.arrived_at
        instance = super().update(instance, validated_data)
        new_status = instance.status
        # 상태 변경 이력
        if old_status != new_status:
            IncidentStatusHistory.objects.create(
                incident=instance, from_status=old_status, to_status=new_status,
                changed_by=self.context['request'].user
            )
        # SLA 갱신: 도착 또는 완료 시
        arrived_changed = instance.arrived_at and instance.arrived_at != old_arrived_at
        if arrived_changed or (new_status == 'completed' and instance.completed_at):
            self._update_sla(instance)
        return instance

    def _update_sla(self, incident):
        try:
            sla = incident.sla
            sla_fields_changed = []
            incident_sla_fields = []

            # 도착 SLA
            if incident.arrived_at:
                sla.arrival_actual = incident.arrived_at
                arrival_diff = int((incident.arrived_at - incident.received_at).total_seconds() / 60)
                sla.arrival_diff_min = arrival_diff - int(
                    (sla.arrival_target - incident.received_at).total_seconds() / 60
                )
                sla.arrival_ok = incident.arrived_at <= sla.arrival_target
                incident.sla_arrival_ok = sla.arrival_ok
                sla_fields_changed += ['arrival_actual', 'arrival_diff_min', 'arrival_ok']
                incident_sla_fields.append('sla_arrival_ok')

            # 처리 SLA
            if incident.completed_at:
                sla.resolve_actual = incident.completed_at
                resolve_diff = int((incident.completed_at - incident.received_at).total_seconds() / 60)
                sla.resolve_diff_min = resolve_diff - int(
                    (sla.resolve_target - incident.received_at).total_seconds() / 60
                )
                sla.resolve_ok = incident.completed_at <= sla.resolve_target
                incident.sla_resolve_ok = sla.resolve_ok
                sla_fields_changed += ['resolve_actual', 'resolve_diff_min', 'resolve_ok']
                incident_sla_fields.append('sla_resolve_ok')

            if sla_fields_changed:
                sla.save(update_fields=sla_fields_changed)
            if incident_sla_fields:
                incident.save(update_fields=incident_sla_fields)
        except IncidentSLA.DoesNotExist:
            pass


class IncidentAssignmentSerializer(serializers.ModelSerializer):
    worker_name      = serializers.CharField(source='worker.name', read_only=True)
    worker_phone     = serializers.CharField(source='worker.phone', read_only=True)
    worker_lat       = serializers.SerializerMethodField()
    worker_lng       = serializers.SerializerMethodField()

    class Meta:
        model = IncidentAssignment
        fields = ['id', 'incident', 'worker', 'worker_name', 'worker_phone',
                  'worker_lat', 'worker_lng', 'is_ai_assigned', 'distance_km',
                  'eta_minutes', 'accepted_at', 'departed_at', 'arrived_at',
                  'completed_at', 'is_accepted', 'reject_reason', 'assigned_at']

    def get_worker_lat(self, obj):
        try:
            return float(obj.worker.current_location.lat)
        except Exception:
            return None

    def get_worker_lng(self, obj):
        try:
            return float(obj.worker.current_location.lng)
        except Exception:
            return None


class IncidentCommentSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source='author.name', read_only=True)

    class Meta:
        model = IncidentComment
        fields = ['id', 'content', 'is_internal', 'author_name', 'created_at', 'updated_at']
        read_only_fields = ['author_name', 'created_at', 'updated_at']


class IncidentPhotoSerializer(serializers.ModelSerializer):
    class Meta:
        model = IncidentPhoto
        fields = ['id', 'photo_type', 'image', 'caption', 'gps_lat', 'gps_lng', 'uploaded_at']


class SLARuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = SLARule
        fields = '__all__'


class WorkOrderSerializer(serializers.ModelSerializer):
    incident_number    = serializers.CharField(source='incident.incident_number', read_only=True)
    school_name        = serializers.CharField(source='school.name', read_only=True)
    assigned_to_name   = serializers.CharField(source='assigned_to.name', read_only=True, default='')
    created_by_name    = serializers.CharField(source='created_by.name', read_only=True, default='')
    confirmed_by_name  = serializers.CharField(source='confirmed_by.name', read_only=True, default='')
    status_display     = serializers.CharField(source='get_status_display', read_only=True)
    work_type_display  = serializers.CharField(source='get_work_type_display', read_only=True)

    class Meta:
        model  = WorkOrder
        fields = '__all__'
        read_only_fields = ['work_order_number', 'created_at', 'updated_at']
