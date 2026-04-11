from rest_framework import serializers
from .models import AiModel, AiJob, WorkerAssignmentPrediction, IncidentPattern, ImageClassification


class AiModelSerializer(serializers.ModelSerializer):
    type_display = serializers.CharField(source='get_model_type_display', read_only=True)

    class Meta:
        model = AiModel
        fields = ['id', 'name', 'model_type', 'type_display', 'version',
                  'endpoint', 'is_active', 'created_at']
        read_only_fields = ['id', 'created_at']


class AiJobSerializer(serializers.ModelSerializer):
    model_name   = serializers.CharField(source='ai_model.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    duration_sec = serializers.SerializerMethodField()

    class Meta:
        model = AiJob
        fields = ['id', 'ai_model', 'model_name', 'job_type', 'input_data',
                  'output_data', 'status', 'status_display', 'error_msg',
                  'started_at', 'finished_at', 'duration_sec', 'created_at']
        read_only_fields = ['id', 'output_data', 'status', 'error_msg',
                            'started_at', 'finished_at', 'created_at']

    def get_duration_sec(self, obj):
        if obj.started_at and obj.finished_at:
            return (obj.finished_at - obj.started_at).total_seconds()
        return None


class WorkerAssignmentPredictionSerializer(serializers.ModelSerializer):
    worker_name  = serializers.CharField(source='recommended_worker.name', read_only=True)
    worker_phone = serializers.CharField(source='recommended_worker.phone', read_only=True)
    incident_number = serializers.CharField(source='incident.incident_number', read_only=True)

    class Meta:
        model = WorkerAssignmentPrediction
        fields = ['id', 'incident', 'incident_number',
                  'recommended_worker', 'worker_name', 'worker_phone',
                  'distance_km', 'eta_minutes', 'score', 'reason',
                  'is_accepted', 'created_at']
        read_only_fields = ['id', 'created_at']


class IncidentPatternSerializer(serializers.ModelSerializer):
    school_name   = serializers.CharField(source='school.name', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)

    class Meta:
        model = IncidentPattern
        fields = ['id', 'school', 'school_name', 'category', 'category_name',
                  'pattern_type', 'description', 'frequency',
                  'avg_resolve_min', 'analyzed_at']
