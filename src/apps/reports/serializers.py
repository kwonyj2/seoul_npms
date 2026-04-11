from rest_framework import serializers
from .models import ReportTemplate, Report, ReportVersion, ReportSignature


class ReportTemplateSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source='created_by.name', read_only=True)
    type_display    = serializers.CharField(source='get_report_type_display', read_only=True)

    class Meta:
        model = ReportTemplate
        fields = ['id', 'code', 'name', 'report_type', 'type_display',
                  'fields_schema', 'is_active', 'created_by', 'created_by_name', 'created_at']
        read_only_fields = ['id', 'created_at']


class ReportSignatureSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReportSignature
        fields = ['id', 'signer', 'signer_name', 'role',
                  'signature_data', 'signed_at', 'is_valid']
        read_only_fields = ['id', 'signed_at']

    def create(self, validated_data):
        request = self.context.get('request')
        if request and hasattr(request, 'user') and not validated_data.get('signer'):
            validated_data['signer'] = request.user
            validated_data.setdefault('signer_name', request.user.name)
        return super().create(validated_data)


class ReportVersionSerializer(serializers.ModelSerializer):
    saved_by_name = serializers.CharField(source='saved_by.name', read_only=True)

    class Meta:
        model = ReportVersion
        fields = ['id', 'version', 'data', 'saved_by', 'saved_by_name', 'saved_at', 'note']
        read_only_fields = ['id', 'version', 'saved_by', 'saved_at']


class ReportListSerializer(serializers.ModelSerializer):
    school_name    = serializers.CharField(source='school.name', read_only=True)
    template_name  = serializers.CharField(source='template.name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.name', read_only=True)
    incident_number = serializers.CharField(source='incident.incident_number', read_only=True)
    status_display  = serializers.CharField(source='get_status_display', read_only=True)
    signature_count = serializers.SerializerMethodField()

    class Meta:
        model = Report
        fields = ['id', 'title', 'school', 'school_name', 'template', 'template_name',
                  'incident', 'incident_number', 'status', 'status_display',
                  'pdf_path', 'is_final', 'created_by', 'created_by_name',
                  'signature_count', 'completed_at', 'created_at', 'updated_at']

    def get_signature_count(self, obj):
        return obj.signatures.filter(is_valid=True).count()


class ReportDetailSerializer(serializers.ModelSerializer):
    school_name     = serializers.CharField(source='school.name', read_only=True)
    template_name   = serializers.CharField(source='template.name', read_only=True)
    template_type   = serializers.CharField(source='template.report_type', read_only=True)
    created_by_name = serializers.CharField(source='created_by.name', read_only=True)
    versions        = ReportVersionSerializer(many=True, read_only=True)
    signatures      = ReportSignatureSerializer(many=True, read_only=True)

    class Meta:
        model = Report
        fields = ['id', 'title', 'school', 'school_name', 'template', 'template_name',
                  'template_type', 'incident', 'status', 'data', 'pdf_path', 'is_final',
                  'created_by', 'created_by_name', 'versions', 'signatures',
                  'completed_at', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_by', 'created_at', 'updated_at']


class ReportCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Report
        fields = ['id', 'template', 'school', 'incident', 'title', 'data']
        read_only_fields = ['id']

    def create(self, validated_data):
        request = self.context.get('request')
        if request:
            validated_data['created_by'] = request.user
        return super().create(validated_data)
