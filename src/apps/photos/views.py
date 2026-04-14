from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from django.db.models import Q, Count

@login_required
def photos_view(request):
    return render(request, 'photos/index.html')


# ── 스위치 DB 엑셀에서 건물/층/설치장소 조회 ──────────────────────────
import os, logging
from django.conf import settings
from django.http import JsonResponse

_switch_cache = None  # {학교명: [{building, floor, room}, ...]}

def _load_switch_locations():
    """장비목록_스위치.xlsx에서 학교별 건물/층/설치장소 캐시 로드"""
    global _switch_cache
    if _switch_cache is not None:
        return _switch_cache
    import openpyxl
    nas_root = getattr(settings, 'NAS_MEDIA_ROOT', settings.MEDIA_ROOT)
    xlsx_path = os.path.join(nas_root, 'data', '장비목록_스위치.xlsx')
    _switch_cache = {}
    if not os.path.exists(xlsx_path):
        logging.getLogger(__name__).warning(f'스위치 DB 파일 없음: {xlsx_path}')
        return _switch_cache
    wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    ws = wb.active
    for row in ws.iter_rows(min_row=2, values_only=True):
        school_name = str(row[3] or '').strip()
        if not school_name:
            continue
        building = str(row[5] or '').strip()
        floor = str(row[6] or '').strip()
        room = str(row[7] or '').strip()
        if school_name not in _switch_cache:
            _switch_cache[school_name] = []
        loc = {'building': building, 'floor': floor, 'room': room}
        if loc not in _switch_cache[school_name]:
            _switch_cache[school_name].append(loc)
    wb.close()
    return _switch_cache


@login_required
def switch_locations_api(request):
    """학교명으로 스위치 DB의 건물/층/설치장소 조회"""
    school_name = request.GET.get('school_name', '').strip()
    if not school_name:
        return JsonResponse({'locations': []})
    cache = _load_switch_locations()
    locations = cache.get(school_name, [])
    # 고유 건물 목록
    buildings = sorted(set(loc['building'] for loc in locations if loc['building']))
    return JsonResponse({'locations': locations, 'buildings': buildings})


from .models import Photo, PhotoWorkType
from .serializers import PhotoListSerializer, PhotoUploadSerializer, PhotoWorkTypeSerializer
from core.pagination import StandardPagination
from core.permissions.roles import IsAdmin, IsSuperAdmin


class PhotoWorkTypeViewSet(viewsets.ModelViewSet):
    """작업 유형 관리 — 조회: 전체, 등록/수정/삭제: 슈퍼관리자 전용"""
    serializer_class = PhotoWorkTypeSerializer
    permission_classes = [IsAuthenticated]
    queryset = PhotoWorkType.objects.all()   # is_active 무관하게 관리자에게 전체 노출

    def get_queryset(self):
        # 일반 사용자는 활성 작업명만, 슈퍼관리자는 전체
        if self.request.user.role == 'superadmin':
            return PhotoWorkType.objects.all().order_by('order', 'id')
        return PhotoWorkType.objects.filter(is_active=True).order_by('order', 'id')

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsSuperAdmin()]
        return [IsAuthenticated()]


class PhotoViewSet(viewsets.ModelViewSet):
    """현장 작업 사진 CRUD"""
    permission_classes = [IsAuthenticated]
    pagination_class = StandardPagination
    parser_classes = [MultiPartParser, FormParser]

    def get_serializer_class(self):
        if self.action == 'create':
            return PhotoUploadSerializer
        return PhotoListSerializer

    def get_queryset(self):
        user = self.request.user
        qs = Photo.objects.select_related(
            'school__support_center', 'school__school_type',
            'building', 'floor', 'room', 'work_type', 'taken_by', 'incident'
        ).filter(is_deleted=False)
        if user.role == 'worker':
            qs = qs.filter(taken_by=user)

        p = self.request.query_params
        if p.get('center'):
            qs = qs.filter(school__support_center__code=p['center'])
        if p.get('school_type'):
            qs = qs.filter(school__school_type__code=p['school_type'])
        if p.get('school_id'):
            qs = qs.filter(school_id=p['school_id'])
        if p.get('incident_id'):
            qs = qs.filter(incident_id=p['incident_id'])
        if p.get('stage'):
            qs = qs.filter(photo_stage=p['stage'])
        if p.get('work_type_id'):
            qs = qs.filter(work_type_id=p['work_type_id'])
        if p.get('from'):
            qs = qs.filter(taken_at__date__gte=p['from'])
        if p.get('to'):
            qs = qs.filter(taken_at__date__lte=p['to'])
        if p.get('q'):
            qs = qs.filter(
                Q(school__name__icontains=p['q']) |
                Q(work_type__name__icontains=p['q']) |
                Q(work_type_etc__icontains=p['q']) |
                Q(file_name__icontains=p['q'])
            )
        return qs

    @action(detail=True, methods=['post'])
    def classify(self, request, pk=None):
        """AI 분류 재실행"""
        photo = self.get_object()
        from .tasks import classify_photo_ai
        classify_photo_ai.delay(photo.id)
        return Response({'message': 'AI 분류 요청됨'})

    @action(detail=True, methods=['post'])
    def analyze(self, request, pk=None):
        """AI 품질 검사 + 단계 분류 + 불량 감지 종합 분석"""
        photo = self.get_object()
        with photo.image.open('rb') as f:
            img_bytes = f.read()
        from .ai_service import analyze_photo
        result = analyze_photo(photo, img_bytes, save=True)
        return Response(result)

    @action(detail=False, methods=['get'], url_path='quality-issues')
    def quality_issues(self, request):
        """재촬영 필요 사진 목록 (needs_retake=True)"""
        qs = self.get_queryset().filter(needs_retake=True)
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def by_school(self, request):
        """학교별 사진 통계"""
        qs = Photo.objects.values('school__name').annotate(
            cnt=Count('id')
        ).order_by('-cnt')[:20]
        return Response(list(qs))

    def perform_destroy(self, instance):
        """삭제 → 휴지통 (소프트 삭제)"""
        instance.is_deleted = True
        instance.deleted_at = timezone.now()
        instance.save(update_fields=['is_deleted', 'deleted_at'])

    @action(detail=False, methods=['post'])
    def bulk_delete(self, request):
        """선택 사진 일괄 휴지통 이동"""
        ids = request.data.get('ids', [])
        if not ids:
            return Response({'error': '삭제할 사진 ID를 전달하세요.'}, status=status.HTTP_400_BAD_REQUEST)
        qs = Photo.objects.filter(id__in=ids, is_deleted=False)
        if request.user.role not in ('admin', 'manager', 'superadmin'):
            qs = qs.filter(taken_by=request.user)
        cnt = qs.update(is_deleted=True, deleted_at=timezone.now())
        return Response({'deleted': cnt})

    @action(detail=False, methods=['get'])
    def trash(self, request):
        """휴지통 목록"""
        qs = Photo.objects.select_related(
            'school', 'work_type', 'taken_by'
        ).filter(is_deleted=True).order_by('-deleted_at')
        if request.user.role == 'worker':
            qs = qs.filter(taken_by=request.user)
        page = self.paginate_queryset(qs)
        serializer = PhotoListSerializer(page or qs, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def restore(self, request):
        """휴지통에서 복원"""
        ids = request.data.get('ids', [])
        if not ids:
            return Response({'error': '복원할 사진 ID를 전달하세요.'}, status=status.HTTP_400_BAD_REQUEST)
        cnt = Photo.objects.filter(id__in=ids, is_deleted=True).update(
            is_deleted=False, deleted_at=None
        )
        return Response({'restored': cnt})

    @action(detail=False, methods=['post'])
    def permanent_delete(self, request):
        """휴지통에서 영구 삭제"""
        ids = request.data.get('ids', [])
        if not ids:
            return Response({'error': 'ID를 전달하세요.'}, status=status.HTTP_400_BAD_REQUEST)
        import os
        qs = Photo.objects.filter(id__in=ids, is_deleted=True)
        for p in qs:
            if p.nas_path and os.path.exists(p.nas_path):
                os.remove(p.nas_path)
            if p.image and os.path.exists(p.image.path):
                os.remove(p.image.path)
        cnt, _ = qs.delete()
        return Response({'deleted': cnt})

    @action(detail=False, methods=['post'])
    def bulk_upload(self, request):
        """다중 사진 업로드"""
        files = request.FILES.getlist('images')
        if not files:
            return Response({'error': '이미지 파일이 없습니다.'}, status=status.HTTP_400_BAD_REQUEST)
        results = []
        errors  = []
        for f in files:
            data = request.data.copy()
            data['image'] = f
            ser = PhotoUploadSerializer(data=data, context={'request': request})
            if ser.is_valid():
                photo = ser.save()
                results.append(photo.id)
            else:
                errors.append({'file': f.name, 'errors': ser.errors})
        return Response({
            'created': len(results),
            'errors': errors,
            'photo_ids': results,
        }, status=status.HTTP_201_CREATED if results else status.HTTP_400_BAD_REQUEST)
