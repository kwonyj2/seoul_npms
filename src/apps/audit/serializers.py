from rest_framework import serializers
from .models import AuditProject, Requirement, ArtifactTemplate, Artifact, AuditPlan, ChecklistItem, CorrectiveAction, ArtifactFile


class AuditProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model  = AuditProject
        fields = '__all__'


class RequirementSerializer(serializers.ModelSerializer):
    category_display = serializers.CharField(source='get_category_display', read_only=True)
    status_display   = serializers.CharField(source='get_status_display',   read_only=True)
    artifact_count   = serializers.SerializerMethodField()

    class Meta:
        model  = Requirement
        fields = '__all__'

    def get_artifact_count(self, obj):
        return obj.artifacts.count()


class ArtifactTemplateSerializer(serializers.ModelSerializer):
    audit_phase_display  = serializers.CharField(source='get_audit_phase_display',  read_only=True)
    submit_timing_display = serializers.CharField(source='get_submit_timing_display', read_only=True)
    category_display     = serializers.CharField(source='get_category_display',      read_only=True)
    req_code             = serializers.SerializerMethodField()
    req_name             = serializers.SerializerMethodField()
    artifact_status      = serializers.SerializerMethodField()

    class Meta:
        model  = ArtifactTemplate
        fields = '__all__'

    def get_req_code(self, obj):
        return obj.requirement.code if obj.requirement else ''

    def get_req_name(self, obj):
        return obj.requirement.name if obj.requirement else ''

    def get_artifact_status(self, obj):
        art = obj.artifacts.first()
        if art:
            return {
                'id':              art.id,
                'status':          art.status,
                'status_display':  art.get_status_display(),
                'file':            bool(art.file),
                'file_name':       art.file_name or '',
                'occurrence_date': str(art.occurrence_date) if art.occurrence_date else '',
                'location_note':   art.location_note or '',
            }
        return None


class ArtifactSerializer(serializers.ModelSerializer):
    status_display    = serializers.CharField(source='get_status_display',    read_only=True)
    audit_phase_display = serializers.CharField(source='get_audit_phase_display', read_only=True)
    submitted_by_name = serializers.SerializerMethodField()
    template_code     = serializers.SerializerMethodField()
    requirement_codes = serializers.SerializerMethodField()

    class Meta:
        model  = Artifact
        fields = '__all__'

    def get_submitted_by_name(self, obj):
        return obj.submitted_by.name if obj.submitted_by else ''

    def get_template_code(self, obj):
        return obj.template.code if obj.template else ''

    def get_requirement_codes(self, obj):
        return list(obj.requirements.values_list('code', flat=True))


class ArtifactCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Artifact
        fields = '__all__'


class AuditPlanSerializer(serializers.ModelSerializer):
    phase_display    = serializers.CharField(source='get_phase_display',  read_only=True)
    status_display   = serializers.CharField(source='get_status_display', read_only=True)
    checklist_total  = serializers.ReadOnlyField()
    checklist_passed = serializers.ReadOnlyField()
    checklist_pct    = serializers.ReadOnlyField()

    class Meta:
        model  = AuditPlan
        fields = '__all__'


class ChecklistItemSerializer(serializers.ModelSerializer):
    area_display    = serializers.CharField(source='get_area_display',   read_only=True)
    phase_display   = serializers.CharField(source='get_phase_display',  read_only=True)
    result_display  = serializers.CharField(source='get_result_display', read_only=True)
    req_code        = serializers.SerializerMethodField()
    audit_phase_key = serializers.SerializerMethodField()

    class Meta:
        model  = ChecklistItem
        fields = '__all__'

    def get_req_code(self, obj):
        return obj.requirement.code if obj.requirement else ''

    def get_audit_phase_key(self, obj):
        return obj.audit_plan.phase


class CorrectiveActionSerializer(serializers.ModelSerializer):
    type_display      = serializers.CharField(source='get_action_type_display', read_only=True)
    status_display    = serializers.CharField(source='get_status_display',      read_only=True)
    completed_by_name = serializers.SerializerMethodField()
    verified_by_name  = serializers.SerializerMethodField()
    checklist_area    = serializers.SerializerMethodField()
    checklist_desc    = serializers.SerializerMethodField()
    audit_phase       = serializers.SerializerMethodField()

    class Meta:
        model  = CorrectiveAction
        fields = '__all__'

    def get_completed_by_name(self, obj):
        return obj.completed_by.name if obj.completed_by else ''

    def get_verified_by_name(self, obj):
        return obj.verified_by.name if obj.verified_by else ''

    def get_checklist_area(self, obj):
        return obj.checklist_item.get_area_display()

    def get_checklist_desc(self, obj):
        return obj.checklist_item.description[:80]

    def get_audit_phase(self, obj):
        return obj.checklist_item.audit_plan.get_phase_display()


class ArtifactFileSerializer(serializers.ModelSerializer):
    template_code        = serializers.SerializerMethodField()
    template_name        = serializers.SerializerMethodField()
    template_phase       = serializers.SerializerMethodField()
    template_category    = serializers.SerializerMethodField()
    uploaded_by_name     = serializers.SerializerMethodField()
    file_size_display    = serializers.ReadOnlyField()
    ext                  = serializers.ReadOnlyField()
    file_url             = serializers.SerializerMethodField()

    class Meta:
        model  = ArtifactFile
        fields = '__all__'

    def get_template_code(self, obj):
        return obj.template.code if obj.template else ''

    def get_template_name(self, obj):
        return obj.template.name if obj.template else ''

    def get_template_phase(self, obj):
        return obj.template.audit_phase if obj.template else ''

    def get_template_category(self, obj):
        return obj.template.category if obj.template else ''

    def get_uploaded_by_name(self, obj):
        return obj.uploaded_by.name if obj.uploaded_by else ''

    def get_file_url(self, obj):
        if obj.file:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.file.url)
            return obj.file.url
        return ''
