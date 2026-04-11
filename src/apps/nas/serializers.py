from rest_framework import serializers
from .models import Folder, File, FileDownloadLog


class FolderSerializer(serializers.ModelSerializer):
    children_count   = serializers.SerializerMethodField()
    files_count      = serializers.SerializerMethodField()
    school_name      = serializers.CharField(source='school.name', read_only=True)
    created_by_name  = serializers.CharField(source='created_by.name', read_only=True)
    access_level_display = serializers.CharField(source='get_access_level_display', read_only=True)

    class Meta:
        model = Folder
        fields = ['id', 'name', 'parent', 'school', 'school_name',
                  'full_path', 'is_system', 'access_level', 'access_level_display',
                  'created_by', 'created_by_name', 'children_count', 'files_count', 'created_at']
        read_only_fields = ['id', 'full_path', 'created_at']

    def get_children_count(self, obj):
        return obj.children.count()

    def get_files_count(self, obj):
        return obj.files.count()

    def create(self, validated_data):
        parent = validated_data.get('parent')
        name   = validated_data['name']
        if parent:
            validated_data['full_path'] = f'{parent.full_path}/{name}'
        else:
            validated_data['full_path'] = f'/{name}'
        return super().create(validated_data)


class FileSerializer(serializers.ModelSerializer):
    folder_path    = serializers.CharField(source='folder.full_path', read_only=True)
    school_name    = serializers.CharField(source='school.name', read_only=True)
    uploaded_by_name = serializers.CharField(source='uploaded_by.name', read_only=True)
    file_size_kb   = serializers.SerializerMethodField()
    category_display = serializers.CharField(source='get_category_display', read_only=True)

    class Meta:
        model = File
        fields = ['id', 'folder', 'folder_path', 'name', 'original_name',
                  'file_path', 'file_size', 'file_size_kb', 'mime_type',
                  'category', 'category_display', 'school', 'school_name',
                  'description', 'ocr_text', 'uploaded_by', 'uploaded_by_name',
                  'uploaded_at']
        read_only_fields = ['id', 'name', 'file_path', 'file_size', 'mime_type',
                            'ocr_text', 'uploaded_by', 'uploaded_at']

    def get_file_size_kb(self, obj):
        return round(obj.file_size / 1024, 1) if obj.file_size else 0


class FileUploadSerializer(serializers.Serializer):
    folder    = serializers.IntegerField()
    file      = serializers.FileField()
    category  = serializers.ChoiceField(choices=File.CATEGORY_CHOICES, default='other')
    description = serializers.CharField(required=False, allow_blank=True)
