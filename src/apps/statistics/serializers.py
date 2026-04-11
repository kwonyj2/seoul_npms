from rest_framework import serializers
from .models import (
    StatisticsDaily, StatisticsMonthly, SLARecord,
    SatisfactionSurvey, PerformanceMetric
)


class StatisticsDailySerializer(serializers.ModelSerializer):
    sla_arrival_rate = serializers.SerializerMethodField()
    sla_resolve_rate = serializers.SerializerMethodField()
    completion_rate  = serializers.SerializerMethodField()

    class Meta:
        model = StatisticsDaily
        fields = ['id', 'stat_date', 'total_incidents', 'completed_incidents',
                  'sla_arrival_ok', 'sla_resolve_ok', 'sla_arrival_rate', 'sla_resolve_rate',
                  'avg_arrival_min', 'avg_resolve_min', 'active_workers',
                  'completion_rate', 'updated_at']

    def get_sla_arrival_rate(self, obj):
        if obj.total_incidents:
            return round(obj.sla_arrival_ok / obj.total_incidents * 100, 1)
        return None

    def get_sla_resolve_rate(self, obj):
        if obj.total_incidents:
            return round(obj.sla_resolve_ok / obj.total_incidents * 100, 1)
        return None

    def get_completion_rate(self, obj):
        if obj.total_incidents:
            return round(obj.completed_incidents / obj.total_incidents * 100, 1)
        return None


class StatisticsMonthlySerializer(serializers.ModelSerializer):
    support_center_name = serializers.CharField(source='support_center.name', read_only=True)

    class Meta:
        model = StatisticsMonthly
        fields = ['id', 'year', 'month', 'support_center', 'support_center_name',
                  'total_incidents', 'completed_incidents',
                  'sla_arrival_rate', 'sla_resolve_rate',
                  'avg_arrival_min', 'avg_resolve_min', 'avg_satisfaction']


class SLARecordSerializer(serializers.ModelSerializer):
    incident_number = serializers.CharField(source='incident.incident_number', read_only=True)
    school_name     = serializers.CharField(source='incident.school.name', read_only=True)

    class Meta:
        model = SLARecord
        fields = ['id', 'incident', 'incident_number', 'school_name',
                  'arrival_target_min', 'resolve_target_min',
                  'arrival_actual_min', 'resolve_actual_min',
                  'arrival_ok', 'resolve_ok', 'created_at']


class SatisfactionSurveySerializer(serializers.ModelSerializer):
    incident_number = serializers.CharField(source='incident.incident_number', read_only=True)
    school_name     = serializers.CharField(source='incident.school.name', read_only=True)
    status_display  = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = SatisfactionSurvey
        fields = ['id', 'incident', 'incident_number', 'school_name',
                  'sent_to', 'sent_at', 'status', 'status_display',
                  'score', 'comment', 'responded_at']
        read_only_fields = ['id', 'sent_at', 'token']


class SurveyResponseSerializer(serializers.Serializer):
    """만족도 응답 직렬화"""
    token   = serializers.CharField()
    score   = serializers.IntegerField(min_value=1, max_value=5)
    comment = serializers.CharField(required=False, allow_blank=True)
