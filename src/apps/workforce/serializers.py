from rest_framework import serializers
from .models import WorkScheduleType, WorkSchedule, AttendanceLog, AttendanceException, TaskAssignment


class WorkScheduleTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkScheduleType
        fields = ['id', 'code', 'name', 'color', 'order', 'is_active']


class TaskAssignmentSerializer(serializers.ModelSerializer):
    school_name = serializers.CharField(source='school.name', read_only=True)

    class Meta:
        model = TaskAssignment
        fields = ['id', 'school', 'school_name', 'description', 'status',
                  'started_at', 'done_at', 'note', 'order']


class WorkScheduleSerializer(serializers.ModelSerializer):
    worker_name       = serializers.CharField(source='worker.name', read_only=True)
    schedule_type_name= serializers.CharField(source='schedule_type.name', read_only=True)
    schedule_type_color= serializers.CharField(source='schedule_type.color', read_only=True)
    school_name       = serializers.CharField(source='school.name', read_only=True)
    tasks             = TaskAssignmentSerializer(many=True, read_only=True)

    class Meta:
        model = WorkSchedule
        fields = ['id', 'worker', 'worker_name', 'schedule_type', 'schedule_type_name',
                  'schedule_type_color', 'school', 'school_name', 'incident',
                  'title', 'description', 'start_dt', 'end_dt', 'status', 'tasks',
                  'created_at']


class AttendanceLogSerializer(serializers.ModelSerializer):
    worker_name  = serializers.CharField(source='worker.name', read_only=True)
    work_hours   = serializers.SerializerMethodField()
    field_locations = serializers.SerializerMethodField()

    class Meta:
        model = AttendanceLog
        fields = ['id', 'worker', 'worker_name', 'work_date', 'check_in_at', 'check_out_at',
                  'check_in_lat', 'check_in_lng', 'check_out_lat', 'check_out_lng',
                  'check_in_device', 'check_out_device',
                  'status', 'note', 'work_hours', 'field_locations']

    def get_work_hours(self, obj):
        return obj.get_work_hours()

    def get_field_locations(self, obj):
        """같은 날 업무일정의 현장 위치(학교/장애) 목록"""
        schedules = WorkSchedule.objects.filter(
            worker=obj.worker,
            start_dt__date=obj.work_date
        ).select_related('school', 'incident')
        locations = []
        seen = set()
        for s in schedules:
            if s.school and s.school.lat and s.school.lng:
                key = (float(s.school.lat), float(s.school.lng))
                if key not in seen:
                    seen.add(key)
                    locations.append({
                        'name': s.school.name,
                        'lat': float(s.school.lat),
                        'lng': float(s.school.lng),
                        'type': 'school',
                    })
        return locations
