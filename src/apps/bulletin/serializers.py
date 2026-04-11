from rest_framework import serializers
from .models import Post, Attachment


class AttachmentSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model  = Attachment
        fields = ['id', 'filename', 'filesize', 'url', 'uploaded_at']

    def get_url(self, obj):
        request = self.context.get('request')
        if obj.file and request:
            return request.build_absolute_uri(obj.file.url)
        return obj.file.url if obj.file else None


class PostListSerializer(serializers.ModelSerializer):
    author_name      = serializers.CharField(source='author.name', read_only=True)
    category_display = serializers.CharField(source='get_category_display', read_only=True)
    attachment_count = serializers.SerializerMethodField()

    class Meta:
        model  = Post
        fields = ['id', 'category', 'category_display', 'title', 'author',
                  'author_name', 'is_pinned', 'view_count',
                  'attachment_count', 'created_at', 'updated_at']

    def get_attachment_count(self, obj):
        return obj.attachments.count()


class PostDetailSerializer(serializers.ModelSerializer):
    author_name      = serializers.CharField(source='author.name', read_only=True)
    category_display = serializers.CharField(source='get_category_display', read_only=True)
    attachments      = AttachmentSerializer(many=True, read_only=True)

    class Meta:
        model  = Post
        fields = ['id', 'category', 'category_display', 'title', 'content',
                  'author', 'author_name', 'is_pinned', 'view_count',
                  'attachments', 'created_at', 'updated_at']
        read_only_fields = ['id', 'author', 'view_count', 'created_at', 'updated_at']


class PostCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Post
        fields = ['category', 'title', 'content', 'is_pinned']

    def create(self, validated_data):
        request = self.context.get('request')
        if request:
            validated_data['author'] = request.user
        return super().create(validated_data)
