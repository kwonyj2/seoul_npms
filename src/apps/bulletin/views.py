from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from rest_framework import viewsets, permissions, status, parsers
from rest_framework.decorators import action
from rest_framework.response import Response
from django.http import FileResponse, Http404
from django.db.models import Q
import os

from .models import Post, Attachment
from .serializers import (
    PostListSerializer, PostDetailSerializer,
    PostCreateSerializer, AttachmentSerializer,
)
from core.permissions.roles import IsAdmin
from core.pagination import StandardPagination


@login_required
def bulletin_view(request):
    return render(request, 'bulletin/index.html')


class PostViewSet(viewsets.ModelViewSet):
    """게시글 CRUD"""
    permission_classes = [permissions.IsAuthenticated]
    pagination_class   = StandardPagination
    parser_classes     = [parsers.MultiPartParser, parsers.JSONParser]

    def get_serializer_class(self):
        if self.action == 'create':
            return PostCreateSerializer
        if self.action == 'retrieve':
            return PostDetailSerializer
        return PostListSerializer

    def get_queryset(self):
        qs = Post.objects.filter(is_active=True).select_related('author')
        cat = self.request.query_params.get('category')
        if cat:
            qs = qs.filter(category=cat)
        q = self.request.query_params.get('q')
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(content__icontains=q))
        return qs

    def retrieve(self, request, *args, **kwargs):
        """조회수 증가 후 반환"""
        instance = self.get_object()
        Post.objects.filter(pk=instance.pk).update(view_count=instance.view_count + 1)
        instance.refresh_from_db(fields=['view_count'])
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)

    def get_permissions(self):
        """수정·삭제는 작성자 본인 또는 Admin"""
        if self.action in ['update', 'partial_update', 'destroy']:
            return [permissions.IsAuthenticated()]
        return [permissions.IsAuthenticated()]

    @action(detail=True, methods=['post'],
            parser_classes=[parsers.MultiPartParser])
    def upload(self, request, pk=None):
        """파일 첨부 업로드"""
        post = self.get_object()
        files = request.FILES.getlist('files')
        if not files:
            return Response({'error': '파일이 없습니다.'}, status=status.HTTP_400_BAD_REQUEST)
        created = []
        for f in files:
            att = Attachment.objects.create(
                post=post,
                file=f,
                filename=f.name,
                filesize=f.size,
            )
            created.append(AttachmentSerializer(att, context={'request': request}).data)
        return Response(created, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['delete'],
            url_path='attachments/(?P<att_id>[0-9]+)')
    def delete_attachment(self, request, pk=None, att_id=None):
        """첨부파일 삭제"""
        post = self.get_object()
        try:
            att = post.attachments.get(id=att_id)
            if att.file:
                try:
                    os.remove(att.file.path)
                except OSError:
                    pass
            att.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Attachment.DoesNotExist:
            raise Http404

    @action(detail=True, methods=['get'],
            url_path='attachments/(?P<att_id>[0-9]+)/download')
    def download_attachment(self, request, pk=None, att_id=None):
        """첨부파일 다운로드"""
        post = self.get_object()
        try:
            att = post.attachments.get(id=att_id)
            if not att.file or not os.path.exists(att.file.path):
                raise Http404
            return FileResponse(
                open(att.file.path, 'rb'),
                as_attachment=True,
                filename=att.filename,
            )
        except Attachment.DoesNotExist:
            raise Http404
