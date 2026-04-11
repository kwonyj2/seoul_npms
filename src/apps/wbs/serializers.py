from rest_framework import serializers
from .models import WBSItem


class WBSItemSerializer(serializers.ModelSerializer):
    assignee_name         = serializers.CharField(source='assignee.name', read_only=True, default='')
    linked_template_name  = serializers.CharField(source='linked_template.name', read_only=True, default='')
    linked_inspection_name = serializers.CharField(source='linked_inspection.name', read_only=True, default='')
    phase_display         = serializers.CharField(source='get_phase_display', read_only=True)
    progress_source_display = serializers.CharField(source='get_progress_source_display', read_only=True)
    has_children          = serializers.SerializerMethodField()

    class Meta:
        model = WBSItem
        fields = [
            'id', 'project', 'code', 'depth', 'parent', 'phase', 'phase_display',
            'seq', 'name', 'assignee', 'assignee_name', 'weight',
            'planned_start', 'planned_end', 'actual_start', 'actual_end',
            'progress', 'progress_source', 'progress_source_display',
            'linked_template', 'linked_template_name',
            'linked_inspection', 'linked_inspection_name',
            'this_week_plan', 'this_week_actual', 'next_week_plan',
            'is_milestone', 'notes', 'updated_at', 'has_children',
        ]
        read_only_fields = ['updated_at']

    def get_has_children(self, obj):
        return obj.children.exists()


class WBSSummarySerializer(serializers.Serializer):
    """공정준수율 집계 직렬화기"""
    phase            = serializers.CharField()
    phase_display    = serializers.CharField()
    planned_progress = serializers.FloatField()
    actual_progress  = serializers.FloatField()
    compliance_rate  = serializers.FloatField()
    total_weight     = serializers.FloatField()
