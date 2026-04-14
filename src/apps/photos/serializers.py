from rest_framework import serializers
from django.utils import timezone
from .models import Photo, PhotoWorkType


class PhotoWorkTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = PhotoWorkType
        fields = ['id', 'name', 'order', 'is_active']


class PhotoListSerializer(serializers.ModelSerializer):
    school_name    = serializers.CharField(source='school.name', read_only=True)
    work_type_name = serializers.CharField(source='work_type.name', read_only=True)
    taken_by_name  = serializers.CharField(source='taken_by.name', read_only=True)
    stage_display  = serializers.CharField(source='get_photo_stage_display', read_only=True)
    building_name  = serializers.CharField(source='building.name', read_only=True)
    floor_name     = serializers.CharField(source='floor.floor_name', read_only=True)
    room_name      = serializers.CharField(source='room.name', read_only=True)
    image_url      = serializers.SerializerMethodField()

    class Meta:
        model = Photo
        fields = ['id', 'school', 'school_name',
                  'building', 'building_name', 'floor', 'floor_name', 'room', 'room_name',
                  'work_type', 'work_type_name', 'work_type_etc', 'photo_stage', 'stage_display',
                  'image', 'image_url', 'nas_path', 'file_name', 'file_size',
                  'gps_lat', 'gps_lng', 'ai_category', 'ai_confidence',
                  'incident', 'taken_by', 'taken_by_name', 'taken_at', 'uploaded_at',
                  'is_deleted', 'deleted_at']
        read_only_fields = ['id', 'nas_path', 'file_name', 'file_size',
                            'ai_category', 'ai_confidence', 'taken_by', 'uploaded_at']

    def get_image_url(self, obj):
        return obj.image.url if obj.image else None


class PhotoUploadSerializer(serializers.ModelSerializer):
    """현장 사진 업로드"""
    image_url = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Photo
        fields = ['id', 'school', 'building', 'floor', 'room',
                  'work_type', 'work_type_etc', 'photo_stage',
                  'image', 'image_url', 'gps_lat', 'gps_lng', 'gps_accuracy',
                  'incident', 'taken_at']
        read_only_fields = ['id', 'image_url']

    def get_image_url(self, obj):
        # 절대 URL 대신 상대 경로 반환 — 포트 불일치 방지
        return obj.image.url if obj.image else None

    def validate_image(self, value):
        """MIME type + PIL + 파일 크기 검증"""
        from core.validators import validate_image_file, sanitize_filename
        validate_image_file(value)
        # 파일명 sanitize
        value.name = sanitize_filename(value.name)
        return value

    def validate_taken_at(self, value):
        if not value:
            return timezone.now()
        return value

    def create(self, validated_data):
        request = self.context.get('request')
        if request:
            validated_data['taken_by'] = request.user
        photo = super().create(validated_data)
        # 파일명 자동 생성 및 NAS 동기화 (비동기)
        from .tasks import sync_photo_to_nas
        sync_photo_to_nas.delay(photo.id)
        return photo
