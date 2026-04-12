from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from django.http import FileResponse
from django.conf import settings
from django.db.models import Q
from django.utils import timezone
import os
import shutil
import mimetypes

def file_open_view(request, token):
    """임시 토큰으로 파일 제공 (인증 불필요 — Office URI 스킴 전용)"""
    from django.core.cache import cache
    from django.http import HttpResponse
    file_id = cache.get(f'nas_open_{token}')
    if not file_id:
        return HttpResponse('링크가 만료되었거나 유효하지 않습니다.', status=410)
    try:
        file_obj = File.objects.get(pk=file_id)
    except File.DoesNotExist:
        return HttpResponse('파일을 찾을 수 없습니다.', status=404)
    if not os.path.exists(file_obj.file_path):
        return HttpResponse('파일이 서버에 존재하지 않습니다.', status=404)
    return FileResponse(
        open(file_obj.file_path, 'rb'),
        as_attachment=False,
        filename=file_obj.original_name,
        content_type=file_obj.mime_type or 'application/octet-stream',
    )


@login_required
def nas_view(request):
    return render(request, 'nas/index.html')


@login_required
def deliverables_view(request):
    return render(request, 'deliverables/index.html')


from .models import Folder, File, FileDownloadLog
from .serializers import FolderSerializer, FileSerializer, FileUploadSerializer
from core.permissions.roles import IsAdmin
from core.pagination import StandardPagination


class FolderViewSet(viewsets.ModelViewSet):
    """NAS 폴더 관리"""
    serializer_class = FolderSerializer
    permission_classes = [IsAuthenticated]

    def _access_filter(self, qs):
        """사용자 역할에 따라 접근 가능한 폴더만 반환"""
        role = self.request.user.role
        if role == 'superadmin':
            return qs  # 모든 폴더 접근 가능
        if role in ('admin',):
            return qs.exclude(access_level='superadmin')
        # worker, resident, customer 등 일반 사용자
        return qs.filter(access_level='public')

    def get_queryset(self):
        qs = Folder.objects.select_related('school', 'created_by')
        parent_id = self.request.query_params.get('parent_id')
        if parent_id == 'null' or parent_id == '0':
            qs = qs.filter(parent__isnull=True)
        elif parent_id:
            qs = qs.filter(parent_id=parent_id)
        school_id = self.request.query_params.get('school_id')
        if school_id:
            qs = qs.filter(school_id=school_id)
        return self._access_filter(qs)

    def perform_create(self, serializer):
        from rest_framework.exceptions import PermissionDenied
        from apps.sysconfig.models import NasRoleConfig
        role = self.request.user.role
        parent = serializer.validated_data.get('parent')
        if parent is None and role != 'superadmin':
            raise PermissionDenied('최상위 폴더는 슈퍼어드민만 생성할 수 있습니다.')
        if not NasRoleConfig.can_do(role, 'create_folder'):
            raise PermissionDenied('폴더 생성 권한이 없습니다.')
        if parent and 'access_level' not in serializer.validated_data:
            serializer.save(created_by=self.request.user, access_level=parent.access_level)
        else:
            serializer.save(created_by=self.request.user)

    def perform_destroy(self, instance):
        from rest_framework.exceptions import PermissionDenied
        from apps.sysconfig.models import NasRoleConfig
        if not NasRoleConfig.can_do(self.request.user.role, 'delete'):
            raise PermissionDenied('폴더 삭제 권한이 없습니다.')
        instance.delete()

    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        """폴더 전체를 zip으로 압축하여 다운로드"""
        import zipfile
        import io
        from django.http import HttpResponse
        from django.shortcuts import get_object_or_404

        folder = get_object_or_404(Folder, pk=pk)

        # 폴더 하위 모든 파일을 재귀 수집
        def collect_files(f, base_path=''):
            result = []
            rel = f'{base_path}/{f.name}' if base_path else f.name
            for file_obj in f.files.all():
                result.append((file_obj, f'{rel}/{file_obj.name}'))
            for child in f.children.all():
                result.extend(collect_files(child, rel))
            return result

        all_files = collect_files(folder)

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            for file_obj, arc_name in all_files:
                if os.path.exists(file_obj.file_path):
                    zf.write(file_obj.file_path, arc_name)
        buf.seek(0)

        response = HttpResponse(buf, content_type='application/zip')
        safe_name = folder.name.encode('utf-8').decode('latin-1', errors='replace')
        response['Content-Disposition'] = f'attachment; filename="{safe_name}.zip"'
        return response

    @action(detail=True, methods=['patch'])
    def rename(self, request, pk=None):
        """폴더 이름 변경 및 full_path 재귀 갱신"""
        folder = self.get_object()
        new_name = request.data.get('name', '').strip()
        if not new_name:
            return Response({'error': '이름을 입력하세요.'}, status=status.HTTP_400_BAD_REQUEST)
        old_path = folder.full_path
        parent_path = folder.parent.full_path if folder.parent else ''
        new_path = f'{parent_path}/{new_name}'

        def update_paths(f, old_prefix, new_prefix):
            f.full_path = new_prefix + f.full_path[len(old_prefix):]
            f.save(update_fields=['full_path'])
            for child in f.children.all():
                update_paths(child, old_prefix, new_prefix)

        folder.name = new_name
        folder.full_path = new_path
        folder.save(update_fields=['name', 'full_path'])
        for child in folder.children.all():
            update_paths(child, old_path, new_path)
        return Response({'id': folder.id, 'name': folder.name, 'full_path': folder.full_path})

    @action(detail=True, methods=['patch'])
    def move(self, request, pk=None):
        """폴더를 다른 부모로 이동 및 full_path 재귀 갱신"""
        folder = self.get_object()
        new_parent_id = request.data.get('parent')
        if new_parent_id:
            try:
                new_parent = Folder.objects.get(pk=new_parent_id)
            except Folder.DoesNotExist:
                return Response({'error': '대상 폴더를 찾을 수 없습니다.'}, status=status.HTTP_400_BAD_REQUEST)
            if new_parent.full_path.startswith(folder.full_path):
                return Response({'error': '하위 폴더로 이동할 수 없습니다.'}, status=status.HTTP_400_BAD_REQUEST)
            new_path = f'{new_parent.full_path}/{folder.name}'
        else:
            if self.request.user.role != 'superadmin':
                return Response({'error': '최상위로 이동은 슈퍼어드민만 가능합니다.'}, status=status.HTTP_403_FORBIDDEN)
            new_parent = None
            new_path = f'/{folder.name}'

        old_path = folder.full_path

        def update_paths(f, old_prefix, new_prefix):
            f.full_path = new_prefix + f.full_path[len(old_prefix):]
            f.save(update_fields=['full_path'])
            for child in f.children.all():
                update_paths(child, old_prefix, new_prefix)

        folder.parent = new_parent
        folder.full_path = new_path
        folder.save(update_fields=['parent', 'full_path'])
        for child in folder.children.all():
            update_paths(child, old_path, new_path)
        return Response({'id': folder.id, 'full_path': folder.full_path})

    @action(detail=False, methods=['get'])
    def children(self, request):
        """지정 폴더의 직접 자식 폴더 목록 반환 — 파일시스템 기준 실시간 반영
        ?parent_id=<id>  → 해당 폴더의 자식 (파일시스템 스캔)
        ?parent_id=root  → 루트 폴더 목록 (파일시스템 스캔)
        신규 디렉토리는 DB에 자동 등록
        """
        nas_root = getattr(settings, 'NAS_MEDIA_ROOT', settings.MEDIA_ROOT)
        parent_id = request.query_params.get('parent_id', 'root')

        if parent_id in ('root', '0', 'null', None):
            fs_path = nas_root
            fs_rel = ''
            parent_folder = None
        else:
            try:
                parent_folder = Folder.objects.get(pk=parent_id)
                fs_rel = parent_folder.full_path.lstrip('/')
                fs_path = os.path.join(nas_root, fs_rel)
            except Folder.DoesNotExist:
                return Response([])

        if not os.path.isdir(fs_path):
            return Response([])

        result = []
        try:
            entries = sorted(os.listdir(fs_path))
        except PermissionError:
            return Response([])

        for name in entries:
            if name == '.trash':
                continue
            child_fs = os.path.join(fs_path, name)
            if not os.path.isdir(child_fs):
                continue
            child_full_path = f'/{fs_rel}/{name}' if fs_rel else f'/{name}'
            # DB 레코드 없으면 자동 생성
            child_folder, _ = Folder.objects.get_or_create(
                full_path=child_full_path,
                defaults={'name': name, 'parent': parent_folder,
                          'created_by': request.user, 'access_level': 'public'}
            )
            has_children = False
            try:
                has_children = any(
                    os.path.isdir(os.path.join(child_fs, x))
                    for x in os.listdir(child_fs)
                )
            except Exception:
                pass
            result.append({
                'id': child_folder.id,
                'name': child_folder.name,
                'full_path': child_folder.full_path,
                'access_level': child_folder.access_level,
                'has_children': has_children,
            })
        return Response(result)


class FileViewSet(viewsets.ModelViewSet):
    """NAS 파일 관리"""
    serializer_class = FileSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardPagination
    parser_classes = [MultiPartParser, FormParser]

    def get_queryset(self):
        qs = File.objects.select_related('folder', 'school', 'uploaded_by').filter(is_deleted=False)
        folder_id = self.request.query_params.get('folder_id')
        if folder_id:
            qs = qs.filter(folder_id=folder_id)
            # 파일시스템 스캔: 신규 파일 자동 등록 + 없는 파일 자동 제거
            try:
                folder = Folder.objects.get(pk=folder_id)
                nas_root = getattr(settings, 'NAS_MEDIA_ROOT', settings.MEDIA_ROOT)
                fs_path = os.path.join(nas_root, folder.full_path.lstrip('/'))
                if os.path.isdir(fs_path):
                    existing_paths = set(qs.values_list('file_path', flat=True))
                    for name in os.listdir(fs_path):
                        full_path = os.path.join(fs_path, name)
                        if os.path.isfile(full_path) and full_path not in existing_paths:
                            mime_type = mimetypes.guess_type(name)[0] or 'application/octet-stream'
                            File.objects.create(
                                name=name, original_name=name,
                                file_path=full_path,
                                file_size=os.path.getsize(full_path),
                                mime_type=mime_type, folder=folder,
                            )
                    # 없는 파일 DB에서 제거 (휴지통 파일은 제외)
                    missing_ids = [f.id for f in qs if not os.path.exists(f.file_path)]
                    if missing_ids:
                        File.objects.filter(id__in=missing_ids).delete()
                    qs = File.objects.select_related('folder', 'school', 'uploaded_by').filter(folder_id=folder_id, is_deleted=False)
            except Exception:
                pass
        school_id   = self.request.query_params.get('school_id')
        school_name = self.request.query_params.get('school_name')
        if school_id:
            # school FK 일치 OR 파일명·설명에 학교명 포함
            if school_name:
                qs = qs.filter(
                    Q(school_id=school_id) |
                    Q(name__icontains=school_name) |
                    Q(description__icontains=school_name) |
                    Q(folder__full_path__icontains=school_name)
                )
            else:
                qs = qs.filter(school_id=school_id)
        category = self.request.query_params.get('category')
        if category:
            qs = qs.filter(category=category)
        q = self.request.query_params.get('q')
        if q:
            qs = qs.filter(
                Q(name__icontains=q) | Q(description__icontains=q) |
                Q(ocr_text__icontains=q) | Q(school__name__icontains=q)
            )
        # 파일명 키워드 탭 필터
        TAB_KEYWORDS = ['구성도', '선번장', '랙실장도', '장비목록', '건물정보', '장애처리', '정기점검', '소규모', '스위치']
        tab = self.request.query_params.get('tab')
        if tab == '이미지':
            qs = qs.filter(mime_type__startswith='image/')
        elif tab == '기타':
            excl = Q(mime_type__startswith='image/')
            for kw in TAB_KEYWORDS:
                excl |= Q(name__icontains=kw)
            qs = qs.exclude(excl)
        elif tab in TAB_KEYWORDS:
            qs = qs.filter(name__icontains=tab)
        return qs

    def create(self, request, *args, **kwargs):
        """파일 업로드"""
        from rest_framework.exceptions import PermissionDenied
        from apps.sysconfig.models import NasRoleConfig
        if not NasRoleConfig.can_do(request.user.role, 'upload'):
            raise PermissionDenied('파일 업로드 권한이 없습니다.')
        upload_ser = FileUploadSerializer(data=request.data)
        if not upload_ser.is_valid():
            return Response(upload_ser.errors, status=status.HTTP_400_BAD_REQUEST)
        data = upload_ser.validated_data
        uploaded_file = data['file']

        try:
            folder = Folder.objects.get(id=data['folder'])
        except Folder.DoesNotExist:
            return Response({'error': '폴더를 찾을 수 없습니다.'}, status=status.HTTP_400_BAD_REQUEST)

        nas_root = getattr(settings, 'NAS_MEDIA_ROOT', settings.MEDIA_ROOT)
        folder_path = os.path.join(nas_root, folder.full_path.lstrip('/'))
        os.makedirs(folder_path, exist_ok=True)

        # 중복 파일명 처리
        original_name = uploaded_file.name
        safe_name = original_name.replace(' ', '_')
        file_dest = os.path.join(folder_path, safe_name)
        counter = 1
        base, ext = os.path.splitext(safe_name)
        while os.path.exists(file_dest):
            safe_name = f'{base}_{counter}{ext}'
            file_dest = os.path.join(folder_path, safe_name)
            counter += 1

        with open(file_dest, 'wb') as f:
            for chunk in uploaded_file.chunks():
                f.write(chunk)

        mime_type = mimetypes.guess_type(original_name)[0] or 'application/octet-stream'
        file_obj = File.objects.create(
            folder=folder,
            name=safe_name,
            original_name=original_name,
            file_path=file_dest,
            file_size=os.path.getsize(file_dest),
            mime_type=mime_type,
            category=data.get('category', 'other'),
            school=folder.school,
            description=data.get('description', ''),
            uploaded_by=request.user,
        )
        # PDF 및 이미지 파일 OCR + AI 분류 비동기 처리
        if 'pdf' in mime_type or mime_type.startswith('image/'):
            from .tasks import extract_ocr_text, classify_nas_file
            extract_ocr_text.delay(file_obj.id)
            classify_nas_file.delay(file_obj.id)

        return Response(FileSerializer(file_obj).data, status=status.HTTP_201_CREATED)

    def perform_destroy(self, instance):
        """파일을 휴지통으로 이동 (소프트 삭제)"""
        from rest_framework.exceptions import PermissionDenied
        from apps.sysconfig.models import NasRoleConfig
        if not NasRoleConfig.can_do(self.request.user.role, 'delete'):
            raise PermissionDenied('파일 삭제 권한이 없습니다.')
        nas_root = getattr(settings, 'NAS_MEDIA_ROOT', settings.MEDIA_ROOT)
        trash_dir = os.path.join(nas_root, '.trash')
        os.makedirs(trash_dir, exist_ok=True)
        # 원본 경로 보존 후 파일 이동
        original_path = instance.file_path
        trash_name = f'{instance.id}__{instance.name}'
        trash_dest = os.path.join(trash_dir, trash_name)
        try:
            if os.path.exists(original_path):
                shutil.move(original_path, trash_dest)
                instance.file_path = trash_dest
        except Exception:
            pass
        instance.is_deleted = True
        instance.deleted_at = timezone.now()
        instance.deleted_by = self.request.user
        instance.original_path = original_path
        instance.save(update_fields=['is_deleted', 'deleted_at', 'deleted_by', 'original_path', 'file_path'])

    @action(detail=False, methods=['get'])
    def trash(self, request):
        """휴지통 목록"""
        qs = File.objects.select_related('folder', 'deleted_by').filter(is_deleted=True).order_by('-deleted_at')
        page = self.paginate_queryset(qs)
        if page is not None:
            return self.get_paginated_response(FileSerializer(page, many=True).data)
        return Response(FileSerializer(qs, many=True).data)

    @action(detail=True, methods=['post'])
    def restore(self, request, pk=None):
        """휴지통에서 파일 복원"""
        file_obj = File.objects.filter(pk=pk, is_deleted=True).first()
        if not file_obj:
            return Response({'error': '휴지통에 해당 파일이 없습니다.'}, status=status.HTTP_404_NOT_FOUND)
        original_path = file_obj.original_path
        # 원본 경로 폴더 재생성
        try:
            os.makedirs(os.path.dirname(original_path), exist_ok=True)
            if os.path.exists(file_obj.file_path):
                shutil.move(file_obj.file_path, original_path)
        except Exception as e:
            return Response({'error': f'파일 복원 실패: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        file_obj.file_path = original_path
        file_obj.is_deleted = False
        file_obj.deleted_at = None
        file_obj.deleted_by = None
        file_obj.original_path = ''
        file_obj.save(update_fields=['file_path', 'is_deleted', 'deleted_at', 'deleted_by', 'original_path'])
        return Response({'message': '복원 완료', 'id': file_obj.id})

    @action(detail=False, methods=['delete'])
    def empty_trash(self, request):
        """휴지통 비우기 (영구 삭제)"""
        from rest_framework.exceptions import PermissionDenied
        if request.user.role not in ('superadmin', 'admin'):
            raise PermissionDenied('관리자만 휴지통을 비울 수 있습니다.')
        qs = File.objects.filter(is_deleted=True)
        count = 0
        for f in qs:
            try:
                if os.path.exists(f.file_path):
                    os.remove(f.file_path)
            except Exception:
                pass
            f.delete()
            count += 1
        return Response({'message': f'{count}개 파일 영구 삭제 완료'})

    @action(detail=True, methods=['patch'])
    def rename(self, request, pk=None):
        """파일 표시명(original_name) 변경"""
        file_obj = self.get_object()
        new_name = request.data.get('name', '').strip()
        if not new_name:
            return Response({'error': '이름을 입력하세요.'}, status=status.HTTP_400_BAD_REQUEST)
        file_obj.original_name = new_name
        file_obj.save(update_fields=['original_name'])
        return Response({'id': file_obj.id, 'original_name': file_obj.original_name})

    @action(detail=True, methods=['patch'])
    def move(self, request, pk=None):
        """파일을 다른 폴더로 이동"""
        file_obj = self.get_object()
        folder_id = request.data.get('folder')
        if not folder_id:
            return Response({'error': 'folder 필드가 필요합니다.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            folder = Folder.objects.get(pk=folder_id)
        except Folder.DoesNotExist:
            return Response({'error': '대상 폴더를 찾을 수 없습니다.'}, status=status.HTTP_400_BAD_REQUEST)
        file_obj.folder = folder
        file_obj.school = folder.school
        file_obj.save(update_fields=['folder', 'school'])
        return Response({'id': file_obj.id, 'folder': folder.id, 'folder_path': folder.full_path})

    @action(detail=True, methods=['post'])
    def ocr_retry(self, request, pk=None):
        """OCR 재추출 요청"""
        file_obj = self.get_object()
        file_obj.ocr_text = ''
        file_obj.save(update_fields=['ocr_text'])
        from .tasks import extract_ocr_text
        extract_ocr_text.delay(file_obj.id)
        return Response({'message': 'OCR 재추출 요청됨'})

    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        """파일 다운로드"""
        from rest_framework.exceptions import PermissionDenied
        from apps.sysconfig.models import NasRoleConfig
        if not NasRoleConfig.can_do(request.user.role, 'download'):
            raise PermissionDenied('파일 다운로드 권한이 없습니다.')
        file_obj = self.get_object()
        if not os.path.exists(file_obj.file_path):
            return Response({'error': '파일이 존재하지 않습니다.'}, status=status.HTTP_404_NOT_FOUND)
        FileDownloadLog.objects.create(
            file=file_obj,
            user=request.user,
            ip_address=request.META.get('REMOTE_ADDR'),
        )
        return FileResponse(
            open(file_obj.file_path, 'rb'),
            as_attachment=True,
            filename=file_obj.original_name,
            content_type=file_obj.mime_type or 'application/octet-stream'
        )

    @action(detail=True, methods=['get'])
    def temp_url(self, request, pk=None):
        """Office URI 스킴용 임시 다운로드 토큰 발급 (5분 유효)"""
        import uuid
        from urllib.parse import urlparse
        from django.core.cache import cache
        file_obj = self.get_object()
        token = uuid.uuid4().hex
        cache.set(f'nas_open_{token}', file_obj.id, timeout=300)
        # nginx가 Host 헤더에서 포트를 제거하므로 Referer에서 origin 추출
        referer = request.META.get('HTTP_REFERER', '')
        if referer:
            p = urlparse(referer)
            origin = f'{p.scheme}://{p.netloc}'
        else:
            origin = request.build_absolute_uri('/').rstrip('/')
        url = f'{origin}/npms/nas/open/{token}/'
        return Response({'url': url, 'token': token})

    @action(detail=True, methods=['get'])
    def preview(self, request, pk=None):
        """이미지/PDF 인라인 미리보기"""
        file_obj = self.get_object()
        if not os.path.exists(file_obj.file_path):
            return Response({'error': '파일이 존재하지 않습니다.'}, status=status.HTTP_404_NOT_FOUND)
        mime = file_obj.mime_type or 'application/octet-stream'
        response = FileResponse(
            open(file_obj.file_path, 'rb'),
            content_type=mime,
            as_attachment=False,
        )
        # iframe 내 표시 허용 (기본값 DENY → SAMEORIGIN으로 완화)
        response['X-Frame-Options'] = 'SAMEORIGIN'
        response['Content-Disposition'] = f'inline; filename="{file_obj.original_name}"'
        return response

    @action(detail=False, methods=['get'])
    def search(self, request):
        """전문 검색: 파일명, 설명, OCR 텍스트, 학교명 통합 검색"""
        q = request.query_params.get('q', '').strip()
        if not q:
            return Response({'results': [], 'count': 0})

        qs = File.objects.select_related('folder', 'school', 'uploaded_by').filter(
            Q(name__icontains=q) |
            Q(original_name__icontains=q) |
            Q(description__icontains=q) |
            Q(ocr_text__icontains=q) |
            Q(school__name__icontains=q)
        )

        # 추가 필터
        school_id = request.query_params.get('school_id')
        if school_id:
            qs = qs.filter(school_id=school_id)
        category = request.query_params.get('category')
        if category:
            qs = qs.filter(category=category)

        total = qs.count()
        page = self.paginate_queryset(qs)
        if page is not None:
            return self.get_paginated_response(FileSerializer(page, many=True).data)
        return Response({'results': FileSerializer(qs[:50], many=True).data, 'count': total})

    @action(detail=False, methods=['get'])
    def stats(self, request):
        """NAS 통계: 카테고리별 파일 수 / 용량"""
        from django.db.models import Sum, Count
        qs = File.objects.all()
        school_id = request.query_params.get('school_id')
        if school_id:
            qs = qs.filter(school_id=school_id)

        by_cat = qs.values('category').annotate(
            count=Count('id'),
            total_size=Sum('file_size'),
        )
        total_size = qs.aggregate(s=Sum('file_size'))['s'] or 0
        return Response({
            'total_files': qs.count(),
            'total_size_mb': round(total_size / 1024 / 1024, 2),
            'by_category': list(by_cat),
        })
