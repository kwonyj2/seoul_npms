from rest_framework import serializers
from .models import InspectionPlan, SchoolInspection, Holiday, WorkerArea, InspectionUploadLog


# ──────────────────────────────────────────────────
# 휴일
# ──────────────────────────────────────────────────
class HolidaySerializer(serializers.ModelSerializer):
    holiday_type_display = serializers.CharField(source='get_holiday_type_display', read_only=True)

    class Meta:
        model  = Holiday
        fields = ['id', 'name', 'holiday_type', 'holiday_type_display',
                  'month', 'day', 'specific_date', 'is_recurring',
                  'is_active', 'note', 'created_at']
        read_only_fields = ['id', 'created_at']


# ──────────────────────────────────────────────────
# 인력-담당구역
# ──────────────────────────────────────────────────
class WorkerAreaSerializer(serializers.ModelSerializer):
    worker_name        = serializers.CharField(source='worker.name', read_only=True)
    support_center_name = serializers.CharField(source='support_center.name', read_only=True)

    class Meta:
        model  = WorkerArea
        fields = ['id', 'worker', 'worker_name',
                  'support_center', 'support_center_name',
                  'is_primary', 'created_at']
        read_only_fields = ['id', 'created_at']


# ──────────────────────────────────────────────────
# 업로드 이력
# ──────────────────────────────────────────────────
class InspectionUploadLogSerializer(serializers.ModelSerializer):
    uploaded_by_name = serializers.CharField(source='uploaded_by.name', read_only=True)

    class Meta:
        model  = InspectionUploadLog
        fields = ['id', 'plan', 'uploaded_by', 'uploaded_by_name',
                  'file_name', 'total_rows', 'matched_count',
                  'failed_count', 'added_count', 'result_json', 'uploaded_at']
        read_only_fields = ['id', 'uploaded_at']


# ──────────────────────────────────────────────────
# 학교별 점검
# ──────────────────────────────────────────────────
class SchoolInspectionSerializer(serializers.ModelSerializer):
    school_name        = serializers.CharField(source='school.name', read_only=True)
    center_name        = serializers.CharField(source='school.support_center.name', read_only=True)
    school_type_name   = serializers.CharField(source='school.school_type.name', read_only=True, default='')
    worker_name        = serializers.CharField(source='assigned_worker.name', read_only=True)
    status_display     = serializers.CharField(source='get_status_display', read_only=True)
    priority_display   = serializers.CharField(source='get_priority_display', read_only=True)
    report_title       = serializers.CharField(source='report.title', read_only=True)
    replaced_from_name = serializers.CharField(source='replaced_from.name', read_only=True)

    class Meta:
        model  = SchoolInspection
        fields = ['id', 'plan', 'school', 'school_name', 'center_name', 'school_type_name',
                  'assigned_worker', 'worker_name',
                  'status', 'status_display',
                  'priority', 'priority_display',
                  'task_type',
                  'scheduled_date', 'completed_date',
                  'work_schedule',
                  'replaced_from', 'replaced_from_name', 'replaced_at',
                  'report', 'report_title', 'notes',
                  'created_at', 'updated_at']
        read_only_fields = ['id', 'replaced_from', 'replaced_at', 'created_at', 'updated_at']


# ──────────────────────────────────────────────────
# 점검 계획 목록
# ──────────────────────────────────────────────────
class InspectionPlanListSerializer(serializers.ModelSerializer):
    plan_type_display  = serializers.CharField(source='get_plan_type_display', read_only=True)
    status_display     = serializers.CharField(source='get_status_display', read_only=True)
    created_by_name    = serializers.CharField(source='created_by.name', read_only=True)
    total              = serializers.ReadOnlyField()
    completed_count    = serializers.ReadOnlyField()
    progress_pct       = serializers.ReadOnlyField()

    class Meta:
        model  = InspectionPlan
        fields = ['id', 'name', 'plan_type', 'plan_type_display', 'year', 'quarter',
                  'start_date', 'end_date', 'status', 'status_display',
                  'created_by', 'created_by_name',
                  'total', 'completed_count', 'progress_pct',
                  'created_at']


# ──────────────────────────────────────────────────
# 점검 계획 상세
# ──────────────────────────────────────────────────
class InspectionPlanDetailSerializer(serializers.ModelSerializer):
    plan_type_display  = serializers.CharField(source='get_plan_type_display', read_only=True)
    status_display     = serializers.CharField(source='get_status_display', read_only=True)
    created_by_name    = serializers.CharField(source='created_by.name', read_only=True)
    total              = serializers.ReadOnlyField()
    completed_count    = serializers.ReadOnlyField()
    progress_pct       = serializers.ReadOnlyField()
    school_inspections = SchoolInspectionSerializer(many=True, read_only=True)
    upload_logs        = InspectionUploadLogSerializer(many=True, read_only=True)

    class Meta:
        model  = InspectionPlan
        fields = ['id', 'name', 'plan_type', 'plan_type_display', 'year', 'quarter',
                  'start_date', 'end_date', 'description', 'status', 'status_display',
                  'created_by', 'created_by_name',
                  'total', 'completed_count', 'progress_pct',
                  'school_inspections', 'upload_logs', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_by', 'created_at', 'updated_at']


# ──────────────────────────────────────────────────
# 점검 계획 수정
# ──────────────────────────────────────────────────
class InspectionPlanUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model  = InspectionPlan
        fields = ['name', 'plan_type', 'year', 'quarter',
                  'start_date', 'end_date', 'description', 'status']


# ──────────────────────────────────────────────────
# 점검 계획 생성
# ──────────────────────────────────────────────────
class InspectionPlanCreateSerializer(serializers.ModelSerializer):
    school_ids = serializers.ListField(
        child=serializers.IntegerField(), write_only=True, required=False
    )

    class Meta:
        model  = InspectionPlan
        fields = ['name', 'plan_type', 'year', 'quarter',
                  'start_date', 'end_date', 'description', 'status', 'school_ids']

    def create(self, validated_data):
        school_ids = validated_data.pop('school_ids', [])
        request = self.context.get('request')
        if request:
            validated_data['created_by'] = request.user
        plan = super().create(validated_data)
        if school_ids:
            from apps.schools.models import School
            schools = School.objects.filter(id__in=school_ids, is_active=True)
            SchoolInspection.objects.bulk_create([
                SchoolInspection(plan=plan, school=s) for s in schools
            ])
        return plan
