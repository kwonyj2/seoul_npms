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
    image_url      = serializers.SerializerMethodField()

    class Meta:
        model = Photo
        fields = ['id', 'school', 'school_name',
                  'building_name', 'floor_name', 'room_name',
                  'work_type', 'work_type_name', 'work_type_etc', 'photo_stage', 'stage_display',
                  'image', 'image_url', 'nas_path', 'file_name', 'file_size',
                  'ai_category', 'ai_confidence',
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
        fields = ['id', 'school', 'building_name', 'floor_name', 'room_name',
                  'work_type', 'work_type_etc', 'photo_stage',
                  'image', 'image_url', 'taken_at', 'report_type']
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
        import os, re, shutil
        from django.conf import settings

        request = self.context.get('request')
        if request:
            validated_data['taken_by'] = request.user
        photo = super().create(validated_data)

        # ── 규칙 파일명 즉시 적용 ──
        try:
            school = photo.school
            work_label = photo.work_type.name if photo.work_type else (photo.work_type_etc or '기타')
            stage_label = photo.get_photo_stage_display()

            location_parts = [school.name]
            if photo.building_name:
                location_parts.append(photo.building_name)
            if photo.floor_name:
                location_parts.append(f'{photo.floor_name}')
            if photo.room_name:
                location_parts.append(photo.room_name)
            location = ' '.join(location_parts)

            seq = Photo.objects.filter(
                school=school,
                taken_at__date=(photo.taken_at or timezone.now()).date(),
                work_type=photo.work_type,
                photo_stage=photo.photo_stage,
                id__lte=photo.id,
            ).count()

            ext = os.path.splitext(photo.image.name)[1].lower() if photo.image else '.jpg'
            if ext not in ('.jpg', '.jpeg', '.png', '.gif', '.webp'):
                ext = '.jpg'

            new_name = f"2026년 테크센터-{work_label}_{location}_{stage_label}_{seq:02d}{ext}"
            new_name = re.sub(r'[\\/:*?"<>|]', '', new_name)

            # 파일 이동
            old_path = photo.image.path
            new_rel = f'photos/{new_name}'
            new_path = os.path.join(settings.MEDIA_ROOT, new_rel)
            os.makedirs(os.path.dirname(new_path), exist_ok=True)
            if os.path.exists(old_path):
                shutil.move(old_path, new_path)
                photo.image.name = new_rel
                photo.file_name = new_name
                photo.file_size = os.path.getsize(new_path)
                photo.save(update_fields=['image', 'file_name', 'file_size'])
        except Exception:
            pass

        # NAS 동기화 (비동기)
        from .tasks import sync_photo_to_nas
        sync_photo_to_nas.delay(photo.id)
        return photo
