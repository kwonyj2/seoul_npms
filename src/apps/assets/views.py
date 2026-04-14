"""
assets 앱 Views
자재관리(materials) 구조를 기반으로 장비관리에 맞게 구현
교육청 제공 장비 전체 관리: 창고 → 센터 → 학교
"""
import csv
import io
import os
from datetime import date as dt_date

from django.shortcuts import render
from django.http import FileResponse, Http404, HttpResponse
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.db import transaction
from django.db.models import Q, Count

from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import (
    AssetCategory, AssetModel, Asset,
    AssetInbound, AssetOutbound, AssetReturn,
    AssetHistory, AssetRMA,
    DeviceNetworkConfig, AssetModelConfig,
)
from .serializers import (
    AssetCategorySerializer, AssetModelSerializer,
    AssetListSerializer, AssetDetailSerializer,
    AssetInboundSerializer, AssetOutboundSerializer, AssetReturnSerializer,
    AssetHistorySerializer, AssetRMASerializer,
    DeviceNetworkConfigSerializer, AssetModelConfigSerializer,
)
from core.permissions.roles import IsAdmin, IsSuperAdmin


@login_required
def assets_view(request):
    return render(request, 'assets/index.html')


class NoPaginateMixin:
    """?no_page=1 파라미터 시 페이지네이션 없이 전체 결과 반환 (Excel 다운로드용)"""
    def paginate_queryset(self, queryset):
        if self.request.query_params.get('no_page'):
            return None
        return super().paginate_queryset(queryset)


# ─────────────────────────────────────
# 분류 / 모델
# ─────────────────────────────────────

class AssetCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AssetCategory.objects.all()
    serializer_class = AssetCategorySerializer
    permission_classes = [permissions.IsAuthenticated]


class AssetModelViewSet(viewsets.ModelViewSet):
    queryset = AssetModel.objects.select_related('category').filter(is_active=True)
    serializer_class = AssetModelSerializer
    permission_classes = [permissions.IsAuthenticated]


# ─────────────────────────────────────
# Asset (장비)
# ─────────────────────────────────────

class AssetViewSet(NoPaginateMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = Asset.objects.select_related(
            'asset_model', 'asset_model__category',
            'current_school', 'current_center',
            'replaced_from',
        )
        p = self.request.query_params
        status_      = p.get('status')
        school       = p.get('school')
        center       = p.get('center')
        model_id     = p.get('model')
        category     = p.get('category')
        rma_only     = p.get('rma_replaced')
        install_year = p.get('install_year')
        project      = p.get('project')
        q            = p.get('q')

        if status_:
            qs = qs.filter(status=status_)
        if school:
            qs = qs.filter(current_school_id=school)
        if center:
            qs = qs.filter(current_center_id=center)
        if model_id:
            qs = qs.filter(asset_model_id=model_id)
        if category:
            qs = qs.filter(asset_model__category__code=category)
        if rma_only == '1':
            qs = qs.filter(is_rma_replaced=True)
        if install_year:
            qs = qs.filter(install_year=install_year)
        if project:
            qs = qs.filter(project_name__icontains=project)
        if q:
            qs = qs.filter(
                Q(serial_number__icontains=q) |
                Q(asset_tag__icontains=q) |
                Q(asset_model__model_name__icontains=q) |
                Q(project_name__icontains=q)
            )
        sn_suffix = p.get('sn_suffix')
        if sn_suffix:
            qs = qs.filter(serial_number__iendswith=sn_suffix)
        return qs.order_by('asset_model__category__order', 'asset_model__model_name', 'serial_number')

    def get_serializer_class(self):
        if self.action == 'list':
            return AssetListSerializer
        return AssetDetailSerializer

    def perform_update(self, serializer):
        old = self.get_object()
        instance = serializer.save()
        # 정보 수정 이력 기록
        AssetHistory.objects.create(
            asset=instance, action='edit',
            from_location='', to_location='',
            worker=self.request.user,
            note='장비 정보 수정'
        )

    # ── 통계 ──────────────────────────────
    @action(detail=False, methods=['get'])
    def stats(self, request):
        from django.db.models import Count
        total     = Asset.objects.count()
        warehouse = Asset.objects.filter(status='warehouse').count()
        center    = Asset.objects.filter(status='center').count()
        installed = Asset.objects.filter(status='installed').count()
        rma       = Asset.objects.filter(status='rma').count()
        disposed  = Asset.objects.filter(status='disposed').count()
        replaced  = Asset.objects.filter(is_rma_replaced=True).count()

        # 사업연도별 현황
        by_year = list(
            Asset.objects.filter(install_year__isnull=False)
            .values('install_year')
            .annotate(count=Count('id'))
            .order_by('install_year')
        )
        # 사업명별 현황
        by_project = list(
            Asset.objects.exclude(project_name='')
            .values('project_name')
            .annotate(count=Count('id'))
            .order_by('-count')
        )
        # 분류별 현황
        by_category = list(
            Asset.objects.values(
                'asset_model__category__code',
                'asset_model__category__name',
            )
            .annotate(
                total=Count('id'),
                installed=Count('id', filter=Q(status='installed')),
                center=Count('id', filter=Q(status='center')),
                warehouse=Count('id', filter=Q(status='warehouse')),
                rma=Count('id', filter=Q(status='rma')),
                disposed=Count('id', filter=Q(status='disposed')),
            )
            .order_by('asset_model__category__code')
        )

        return Response({
            'total': total,
            'warehouse': warehouse,
            'center': center,
            'installed': installed,
            'rma': rma,
            'disposed': disposed,
            'rma_replaced': replaced,
            'by_year':     by_year,
            'by_project':  by_project,
            'by_category': by_category,
        })

    # ── 장비별 이력 ─────────────────────────
    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        asset = self.get_object()
        return Response(AssetHistorySerializer(asset.history.all(), many=True).data)

    # ── 센터별 장비 현황 (슈퍼관리자) ──────────
    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated])
    def center_dashboard(self, request):
        """
        센터 선택 → 해당 센터 보유 장비 + 입고/출고/반납 이력 전체 조회
        GET /assets/api/assets/center_dashboard/?center=<id>
        슈퍼관리자: 모든 센터 조회 가능
        일반사용자: 본인 센터만
        """
        from apps.schools.models import SupportCenter
        user = request.user
        center_id = request.query_params.get('center')

        if user.role not in ('superadmin', 'admin'):
            center_id = getattr(user, 'support_center_id', None)
            if not center_id:
                return Response({'error': '소속 지원청 없음'}, status=status.HTTP_400_BAD_REQUEST)

        if not center_id:
            # 센터 목록만 반환
            centers = SupportCenter.objects.all().values('id', 'name', 'code')
            return Response({'centers': list(centers)})

        try:
            center = SupportCenter.objects.get(id=center_id)
        except SupportCenter.DoesNotExist:
            return Response({'error': '센터 없음'}, status=status.HTTP_404_NOT_FOUND)

        # 현재 센터 보관 장비
        center_assets = Asset.objects.filter(
            current_center=center
        ).select_related('asset_model', 'asset_model__category', 'current_school').order_by('status', 'asset_model__model_name')

        # 이 센터에서 나가 학교 설치 중인 장비
        installed_assets = Asset.objects.filter(
            status='installed'
        ).select_related('asset_model', 'asset_model__category', 'current_school').filter(
            outbounds__from_center=center
        ).distinct()

        # 입고 이력 (이 센터로 들어온 것)
        inbounds = AssetInbound.objects.filter(to_center=center).select_related(
            'asset', 'asset__asset_model', 'received_by'
        ).order_by('-inbound_date')[:50]

        # 출고 이력 (이 센터에서 나간 것)
        outbounds = AssetOutbound.objects.filter(from_center=center).select_related(
            'asset', 'asset__asset_model', 'to_center', 'to_school', 'issued_by'
        ).order_by('-outbound_date')[:50]

        # 반납 이력 (이 센터로 돌아온 것)
        returns = AssetReturn.objects.filter(to_center=center).select_related(
            'asset', 'asset__asset_model', 'from_school', 'received_by'
        ).order_by('-return_date')[:50]

        return Response({
            'center': {'id': center.id, 'name': center.name},
            'summary': {
                'in_center':  center_assets.filter(status='center').count(),
                'installed':  installed_assets.count(),
                'total_managed': center_assets.count() + installed_assets.count(),
            },
            'center_assets':    AssetListSerializer(center_assets, many=True).data,
            'installed_assets': AssetListSerializer(installed_assets, many=True).data,
            'inbounds':  AssetInboundSerializer(inbounds, many=True).data,
            'outbounds': AssetOutboundSerializer(outbounds, many=True).data,
            'returns':   AssetReturnSerializer(returns, many=True).data,
        })

    # ── CSV 다운로드 (장비 목록) ─────────────
    @action(detail=False, methods=['get'])
    def csv_download(self, request):
        response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
        response['Content-Disposition'] = 'attachment; filename="asset_list.csv"'
        writer = csv.writer(response)
        writer.writerow([
            '관리번호', '제조번호(S/N)', '분류', '제조사', '모델명',
            '상태', '현재센터', '설치학교', '설치위치',
            '설치연도', '사업명',
            '구매일', '설치일', '보증만료일',
            'RMA교체품여부', '원본S/N', '비고',
        ])
        for a in self.get_queryset():
            writer.writerow([
                a.asset_tag or '',
                a.serial_number,
                a.asset_model.category.name if a.asset_model and a.asset_model.category else '',
                a.asset_model.manufacturer if a.asset_model else '',
                a.asset_model.model_name if a.asset_model else '',
                a.get_status_display(),
                a.current_center.name if a.current_center else '',
                a.current_school.name if a.current_school else '',
                a.install_location or '',
                a.install_year or '',
                a.project_name or '',
                a.purchased_at or '',
                a.installed_at or '',
                a.warranty_expire or '',
                'Y' if a.is_rma_replaced else 'N',
                a.replaced_from.serial_number if a.replaced_from else '',
                a.note or '',
            ])
        return response

    # ── CSV 장비 일괄 등록 (관리자+) ─────────
    @action(detail=False, methods=['get'])
    def csv_register_template(self, request):
        """장비 등록 CSV 양식"""
        response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
        response['Content-Disposition'] = 'attachment; filename="asset_register_template.csv"'
        writer = csv.writer(response)
        writer.writerow(['분류코드', '제조번호(S/N)', '모델명', '제조사', '설치일', '설치학교명', '상태', '설치연도', '사업명', '비고'])
        writer.writerow(['스위치', 'SN000001', 'C3100-24TL', '코어엣지', '', '', '창고', '', '', '창고 보관'])
        writer.writerow(['PoE스위치', 'SN000002', 'CS-48FP', '코어엣지', '2024-03-01', '○○초등학교', '설치됨', '2024', '2024년 학교정보화지원체계(테크센터) 운영지원사업(강북권)', ''])
        writer.writerow(['AP', 'SN000003', 'AP-3650AX', '에이텐', '2026-03-01', '△△중학교', '설치됨', '2026', '2026년 학교 디지털 인프라 통합관리(테크센터) 운영', ''])
        return response

    @action(detail=False, methods=['post'], permission_classes=[IsAdmin])
    def csv_register(self, request):
        """장비 일괄 등록 CSV 업로드"""
        f = request.FILES.get('file')
        if not f:
            return Response({'error': 'CSV 파일을 첨부해 주세요.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            decoded = f.read().decode('utf-8-sig')
        except UnicodeDecodeError:
            decoded = f.read().decode('cp949', errors='replace')

        from apps.schools.models import School
        reader = csv.DictReader(io.StringIO(decoded))
        created, skipped, errors = 0, 0, []

        # 한글 분류코드 → 내부코드 매핑
        KO_CATEGORY_MAP = {
            '스위치':    'switch',
            'poe스위치': 'poe_switch',
            'PoE스위치': 'poe_switch',
            'POE스위치': 'poe_switch',
            'ap':        'ap',
            'AP':        'ap',
            '라우터':    'router',
            '서버':      'server',
            '기타':      'other',
        }
        # 한글 상태 → 내부코드 매핑
        KO_STATUS_MAP = {
            '창고':  'warehouse',
            '센터':  'center',
            '설치됨': 'installed',
            '설치':  'installed',
            'rma':   'rma',
            'RMA':   'rma',
            '폐기':  'disposed',
            '반납':  'returned',
        }

        for row_num, row in enumerate(reader, start=2):
            try:
                sn = (row.get('제조번호(S/N)') or row.get('제조번호') or '').strip()
                if not sn:
                    errors.append(f'{row_num}행: 제조번호(S/N) 필수')
                    continue
                if Asset.objects.filter(serial_number=sn).exists():
                    skipped += 1
                    continue

                cat_raw    = (row.get('분류코드')  or '스위치').strip()
                cat_code   = KO_CATEGORY_MAP.get(cat_raw, KO_CATEGORY_MAP.get(cat_raw.lower(), cat_raw))
                model_name = (row.get('모델명')     or '').strip()
                mfr        = (row.get('제조사')     or '').strip()
                stat_raw   = (row.get('상태')       or '창고').strip()
                stat       = KO_STATUS_MAP.get(stat_raw, stat_raw if stat_raw in dict(Asset.STATUS_CHOICES) else 'warehouse')
                note       = (row.get('비고')       or '').strip()

                cat, _ = AssetCategory.objects.get_or_create(
                    code=cat_code,
                    defaults={'name': cat_raw}
                )
                am, _ = AssetModel.objects.get_or_create(
                    manufacturer=mfr, model_name=model_name,
                    defaults={'category': cat}
                )

                school = None
                center = None
                school_name = (row.get('설치학교명') or '').strip()
                if school_name:
                    school = School.objects.filter(name=school_name).first()

                installed_raw = (row.get('설치일') or '').strip()
                installed_at  = dt_date.fromisoformat(installed_raw) if installed_raw else None

                install_year_raw = (row.get('설치연도') or '').strip()
                install_year = int(install_year_raw) if install_year_raw.isdigit() else None
                project_name = (row.get('사업명') or '').strip()

                # ── 상태 자동 결정 (학교명 기반) ──
                if school:
                    stat = 'installed'
                    center = school.support_center
                elif project_name == '창고':
                    stat = 'warehouse'

                asset = Asset.objects.create(
                    serial_number=sn,
                    asset_model=am,
                    status=stat,
                    current_school=school,
                    current_center=center,
                    installed_at=installed_at,
                    install_year=install_year,
                    project_name=project_name,
                    note=note,
                )
                AssetHistory.objects.create(
                    asset=asset, action='inbound',
                    from_location='CSV 일괄 등록', to_location=asset.get_status_display(),
                    worker=request.user,
                    note='CSV 일괄 등록'
                )

                # ── 창고 장비 → AssetInbound 자동 생성 ──
                if stat == 'warehouse':
                    from .models import AssetInbound
                    inbound_date = dt_date(2026, 5, 1)
                    AssetInbound.objects.create(
                        inbound_number=AssetInbound.generate_number(inbound_date),
                        asset=asset,
                        from_location_type='education_office',
                        from_location_name='서울시교육청',
                        to_location_type='warehouse',
                        inbound_date=inbound_date,
                        received_by=request.user,
                        note='CSV 일괄 등록 자동 입고',
                    )

                created += 1
            except Exception as e:
                errors.append(f'{row_num}행: {e}')

        return Response({'created': created, 'skipped': skipped, 'errors': errors})

    # ── CSV 관리번호 일괄 부여 (관리자+) ─────
    @action(detail=False, methods=['get'])
    def csv_tag_template(self, request):
        """관리번호 부여 CSV 양식"""
        response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
        response['Content-Disposition'] = 'attachment; filename="asset_tag_template.csv"'
        writer = csv.writer(response)
        writer.writerow(['제조번호(S/N)', '관리번호'])
        writer.writerow(['SN000001', 'MGMT-2025-0001'])
        writer.writerow(['SN000002', 'MGMT-2025-0002'])
        return response

    @action(detail=False, methods=['post'], permission_classes=[IsAdmin])
    def csv_tag_upload(self, request):
        """관리번호 일괄 부여 — S/N → 관리번호 매핑"""
        f = request.FILES.get('file')
        if not f:
            return Response({'error': 'CSV 파일을 첨부해 주세요.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            decoded = f.read().decode('utf-8-sig')
        except UnicodeDecodeError:
            decoded = f.read().decode('cp949', errors='replace')

        reader = csv.DictReader(io.StringIO(decoded))
        updated, errors = 0, []

        for row_num, row in enumerate(reader, start=2):
            try:
                sn  = (row.get('제조번호(S/N)') or row.get('제조번호') or '').strip()
                tag = (row.get('관리번호') or '').strip()
                if not sn or not tag:
                    errors.append(f'{row_num}행: 제조번호/관리번호 필수')
                    continue
                try:
                    asset = Asset.objects.get(serial_number=sn)
                except Asset.DoesNotExist:
                    errors.append(f'{row_num}행: S/N [{sn}] 없음')
                    continue
                asset.asset_tag = tag
                asset.save(update_fields=['asset_tag'])
                AssetHistory.objects.create(
                    asset=asset, action='tag',
                    from_location='', to_location='',
                    worker=request.user,
                    note=f'관리번호 부여: {tag}'
                )
                updated += 1
            except Exception as e:
                errors.append(f'{row_num}행: {e}')

        return Response({'updated': updated, 'errors': errors})


# ─────────────────────────────────────
# AssetInbound (장비 입고)
# ─────────────────────────────────────

class AssetInboundViewSet(NoPaginateMixin, viewsets.ModelViewSet):
    queryset = AssetInbound.objects.select_related(
        'asset', 'asset__asset_model', 'asset__asset_model__category',
        'from_center', 'to_center', 'received_by',
    ).order_by('-inbound_date', '-created_at')
    serializer_class = AssetInboundSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_permissions(self):
        if self.action in ('destroy',):
            return [IsAdmin()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        qs = super().get_queryset()
        p  = self.request.query_params
        q        = p.get('q')
        category = p.get('category')
        to_type  = p.get('to_type')
        center   = p.get('center')
        user     = self.request.user

        if q:
            qs = qs.filter(
                Q(asset__serial_number__icontains=q) |
                Q(asset__asset_tag__icontains=q) |
                Q(inbound_number__icontains=q)
            )
        if category:
            qs = qs.filter(asset__asset_model__category__code=category)
        if to_type:
            qs = qs.filter(to_location_type=to_type)
        if center:
            qs = qs.filter(to_center_id=center)
        # 일반사용자: 본인 센터 입고만
        if user.role not in ('superadmin', 'admin'):
            if not getattr(user, 'support_center_id', None):
                return qs.none()
            qs = qs.filter(to_center_id=user.support_center_id)
        return qs

    def perform_create(self, serializer):
        serializer.save(received_by=self.request.user)

    # ── CSV 일괄 입고 양식 ────────────────────
    @action(detail=False, methods=['get'])
    def csv_template(self, request):
        response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
        response['Content-Disposition'] = 'attachment; filename="asset_inbound_template.csv"'
        writer = csv.writer(response)
        writer.writerow(['제조번호(S/N)', '입고일', '출처구분', '출처명칭', '목적지(warehouse/center)',
                          '목적지센터명', '인계자', '인수자', '비고'])
        writer.writerow(['SN000001', '2025-01-15', 'education_office', '서울시교육청',
                          'warehouse', '', '홍길동', '김철수', ''])
        return response

    @action(detail=False, methods=['post'], permission_classes=[IsAdmin])
    def bulk_import(self, request):
        """입고 일괄 등록 CSV"""
        f = request.FILES.get('file')
        if not f:
            return Response({'error': 'CSV 파일을 첨부해 주세요.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            decoded = f.read().decode('utf-8-sig')
        except UnicodeDecodeError:
            decoded = f.read().decode('cp949', errors='replace')

        from apps.schools.models import SupportCenter
        from django.utils import timezone as tz
        reader = csv.DictReader(io.StringIO(decoded))
        created, errors = 0, []

        for row_num, row in enumerate(reader, start=2):
            try:
                sn = (row.get('제조번호(S/N)') or row.get('제조번호') or '').strip()
                if not sn:
                    errors.append(f'{row_num}행: 제조번호 필수')
                    continue
                try:
                    asset = Asset.objects.get(serial_number=sn)
                except Asset.DoesNotExist:
                    errors.append(f'{row_num}행: S/N [{sn}] 없음 — 장비 등록 먼저 필요')
                    continue

                date_str = (row.get('입고일') or '').strip()
                inbound_date = dt_date.fromisoformat(date_str) if date_str else tz.localdate()

                to_type   = (row.get('목적지(warehouse/center)') or 'warehouse').strip()
                to_center = None
                center_name = (row.get('목적지센터명') or '').strip()
                if to_type == 'center' and center_name:
                    to_center = SupportCenter.objects.filter(name=center_name).first()
                    if not to_center:
                        errors.append(f'{row_num}행: 센터 [{center_name}] 없음')
                        continue

                inbound = AssetInbound.objects.create(
                    inbound_number=AssetInbound.generate_number(inbound_date),
                    asset=asset,
                    from_location_type=(row.get('출처구분') or 'education_office').strip(),
                    from_location_name=(row.get('출처명칭') or '').strip(),
                    to_location_type=to_type,
                    to_center=to_center,
                    inbound_date=inbound_date,
                    received_by=request.user,
                    handover_person=(row.get('인계자') or '').strip(),
                    receiver_person=(row.get('인수자') or '').strip(),
                    note=(row.get('비고') or '').strip(),
                )
                # Asset 상태 변경
                if to_type == 'warehouse':
                    asset.status = 'warehouse'
                    asset.current_center = None
                    asset.current_school = None
                elif to_type == 'center' and to_center:
                    asset.status = 'center'
                    asset.current_center = to_center
                    asset.current_school = None
                asset.save(update_fields=['status', 'current_center', 'current_school'])
                AssetHistory.objects.create(
                    asset=asset, action='inbound',
                    from_location=inbound.from_location_name or '',
                    to_location=to_center.name if to_center else '창고',
                    worker=request.user,
                    note=f'CSV 일괄 입고: {inbound.inbound_number}'
                )
                created += 1
            except Exception as e:
                errors.append(f'{row_num}행: {e}')

        return Response({'created': created, 'errors': errors})

    # ── PDF 생성/다운로드/서명 ────────────────
    @action(detail=True, methods=['post'])
    def generate_pdf(self, request, pk=None):
        from .services import generate_inbound_pdf
        try:
            rel_path = generate_inbound_pdf(self.get_object().id)
            return Response({'pdf_path': rel_path, 'url': f'{settings.MEDIA_URL}{rel_path}'})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['get'])
    def download_pdf(self, request, pk=None):
        from .services import generate_inbound_pdf
        inbound = self.get_object()
        if not inbound.pdf_path:
            generate_inbound_pdf(inbound.id)
            inbound.refresh_from_db()
        abs_path = os.path.join(settings.MEDIA_ROOT, inbound.pdf_path)
        if not os.path.exists(abs_path):
            raise Http404
        return FileResponse(
            open(abs_path, 'rb'), content_type='application/pdf',
            as_attachment=True, filename=f'장비입고증_{inbound.inbound_number}.pdf'
        )

    @action(detail=True, methods=['post'])
    def sign(self, request, pk=None):
        inbound = self.get_object()
        fields  = []
        for field in ('handover_signature', 'receiver_signature',
                       'handover_person', 'handover_phone',
                       'receiver_person', 'receiver_phone'):
            val = request.data.get(field, '')
            if val:
                setattr(inbound, field, val)
                fields.append(field)
        if not fields:
            return Response({'error': '저장할 데이터가 없습니다.'}, status=status.HTTP_400_BAD_REQUEST)
        inbound.save(update_fields=fields)
        return Response({'message': '서명 저장 완료'})


# ─────────────────────────────────────
# AssetOutbound (장비 출고)
# ─────────────────────────────────────

class AssetOutboundViewSet(NoPaginateMixin, viewsets.ModelViewSet):
    queryset = AssetOutbound.objects.select_related(
        'asset', 'asset__asset_model', 'asset__asset_model__category',
        'from_center', 'to_center', 'to_school', 'issued_by',
    ).order_by('-outbound_date', '-created_at')
    serializer_class = AssetOutboundSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_permissions(self):
        # 창고 출고(from_warehouse)는 Admin+, 센터 출고는 일반사용자 가능
        if self.action in ('destroy',):
            return [IsAdmin()]
        if self.action in ('create', 'update', 'partial_update'):
            # center_outbound action에서 별도 처리
            return [permissions.IsAuthenticated()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        qs = super().get_queryset()
        p  = self.request.query_params
        q          = p.get('q')
        category   = p.get('category')
        from_type  = p.get('from_type')
        to_type    = p.get('to_type')
        to_center  = p.get('to_center')
        to_school  = p.get('to_school')
        user       = self.request.user

        if q:
            qs = qs.filter(
                Q(asset__serial_number__icontains=q) |
                Q(asset__asset_tag__icontains=q) |
                Q(outbound_number__icontains=q)
            )
        if category:
            qs = qs.filter(asset__asset_model__category__code=category)
        if from_type:
            qs = qs.filter(from_location_type=from_type)
        if to_type:
            qs = qs.filter(to_location_type=to_type)
        if to_center:
            qs = qs.filter(to_center_id=to_center)
        if to_school:
            qs = qs.filter(to_school_id=to_school)
        # 일반사용자: 본인 센터 출고만
        if user.role not in ('superadmin', 'admin'):
            if not getattr(user, 'support_center_id', None):
                return qs.none()
            qs = qs.filter(
                from_location_type='center',
                from_center_id=user.support_center_id
            )
        return qs

    def create(self, request, *args, **kwargs):
        # 창고 출고: Admin+만 가능
        from_type = request.data.get('from_location_type', 'warehouse')
        if from_type == 'warehouse' and not request.user.role in ('superadmin', 'admin'):
            return Response({'error': '창고 출고는 관리자만 가능합니다.'}, status=status.HTTP_403_FORBIDDEN)
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        serializer.save(issued_by=self.request.user)

    # ── 센터→학교 출고 (일반사용자) ──────────
    @action(detail=False, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def center_outbound(self, request):
        """센터에서 학교로 출고 (일반사용자도 가능)"""
        from apps.schools.models import School
        from django.utils import timezone as tz
        user = request.user
        if not getattr(user, 'support_center_id', None):
            return Response({'error': '소속 지원청이 없습니다'}, status=status.HTTP_400_BAD_REQUEST)

        asset_id  = request.data.get('asset')
        school_id = request.data.get('to_school')
        if not asset_id:
            return Response({'error': '장비 선택 필수'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            asset = Asset.objects.select_related('asset_model').get(id=asset_id)
        except Asset.DoesNotExist:
            return Response({'error': '장비 없음'}, status=status.HTTP_404_NOT_FOUND)

        if asset.status != 'center' or asset.current_center_id != user.support_center_id:
            return Response(
                {'error': f'센터 출고 불가: 장비 현재 상태 "{asset.get_status_display()}" / 다른 센터 보관'},
                status=status.HTTP_400_BAD_REQUEST
            )

        date_str = (request.data.get('outbound_date') or '').strip()
        try:
            outbound_date = dt_date.fromisoformat(date_str) if date_str else tz.localdate()
        except ValueError:
            return Response({'error': '출고일 형식 오류 (YYYY-MM-DD)'}, status=status.HTTP_400_BAD_REQUEST)

        school = None
        if school_id:
            school = School.objects.filter(id=school_id).first()

        outbound = AssetOutbound.objects.create(
            outbound_number=AssetOutbound.generate_number(outbound_date),
            asset=asset,
            from_location_type='center',
            from_center_id=user.support_center_id,
            to_location_type='school' if school else 'center',
            to_school=school,
            to_center_id=user.support_center_id if not school else None,
            outbound_date=outbound_date,
            issued_by=user,
            handover_person=(request.data.get('handover_person') or '').strip(),
            receiver_person=(request.data.get('receiver_person') or '').strip(),
            note=(request.data.get('note') or '').strip(),
        )
        # Asset 상태 변경
        if school:
            asset.status = 'installed'
            asset.current_school = school
            if not asset.installed_at:
                asset.installed_at = outbound_date
        asset.save(update_fields=['status', 'current_school', 'installed_at'])
        AssetHistory.objects.create(
            asset=asset, action='outbound',
            from_location=outbound.from_center.name if outbound.from_center else '',
            to_location=school.name if school else '',
            worker=user,
            note=f'출고번호: {outbound.outbound_number}'
        )
        return Response(AssetOutboundSerializer(outbound).data, status=status.HTTP_201_CREATED)

    # ── 현장 교체 (고장 장비 ↔ 정상 장비 교환) ──
    @transaction.atomic
    @action(detail=False, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def school_replace(self, request):
        """
        학교 현장 교체 작업 (atomic)
        - 교체 장비 (센터 보관) → 학교 설치 출고
        - 고장 장비 (학교 설치) → 센터 반납
        두 처리를 한 번에 원자적으로 처리하여 장비 실종 방지
        """
        from django.utils import timezone as tz
        from apps.schools.models import School
        user = request.user

        repl_id   = request.data.get('replacement_asset')   # 교체 장비 (센터 보관 중)
        faulty_id = request.data.get('faulty_asset')        # 고장 장비 (학교 설치 중)
        school_id = request.data.get('school')
        date_str  = (request.data.get('date') or '').strip()
        reason    = (request.data.get('reason') or '장애 교체').strip()
        note      = (request.data.get('note') or '').strip()
        handover_person  = (request.data.get('handover_person') or '').strip()
        handover_phone   = (request.data.get('handover_phone') or '').strip()
        receiver_person  = (request.data.get('receiver_person') or '').strip()
        receiver_phone   = (request.data.get('receiver_phone') or '').strip()

        if not repl_id or not faulty_id:
            return Response({'error': '교체 장비와 고장 장비 모두 선택 필수'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            replace_date = dt_date.fromisoformat(date_str) if date_str else tz.localdate()
        except ValueError:
            return Response({'error': '날짜 형식 오류 (YYYY-MM-DD)'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            repl_asset   = Asset.objects.select_related('asset_model', 'current_center').get(id=repl_id)
            faulty_asset = Asset.objects.select_related('asset_model', 'current_school', 'current_center').get(id=faulty_id)
        except Asset.DoesNotExist:
            return Response({'error': '장비를 찾을 수 없음'}, status=status.HTTP_404_NOT_FOUND)

        # 교체 장비 검증: 센터 보관 중이어야 함
        if repl_asset.status != 'center':
            return Response(
                {'error': f'교체 장비는 센터 보관 상태여야 합니다. 현재: {repl_asset.get_status_display()}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        # 고장 장비 검증: 학교 설치 상태여야 함
        if faulty_asset.status != 'installed':
            return Response(
                {'error': f'고장 장비는 학교 설치 상태여야 합니다. 현재: {faulty_asset.get_status_display()}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        center = repl_asset.current_center
        school = faulty_asset.current_school
        if school_id:
            school = School.objects.filter(id=school_id).first() or school

        if not center:
            return Response({'error': '교체 장비의 소속 센터 정보 없음'}, status=status.HTTP_400_BAD_REQUEST)
        if not school:
            return Response({'error': '고장 장비의 학교 정보 없음'}, status=status.HTTP_400_BAD_REQUEST)

        # ① 교체 장비: 센터 → 학교 출고
        outbound = AssetOutbound.objects.create(
            outbound_number=AssetOutbound.generate_number(replace_date),
            asset=repl_asset,
            from_location_type='center',
            from_center=center,
            to_location_type='school',
            to_school=school,
            outbound_date=replace_date,
            issued_by=user,
            handover_person=handover_person,
            handover_phone=handover_phone,
            receiver_person=receiver_person,
            receiver_phone=receiver_phone,
            note=f'[현장교체] 고장장비 S/N:{faulty_asset.serial_number} 교체 / {note}',
        )
        repl_asset.status = 'installed'
        repl_asset.current_school = school
        repl_asset.current_center = None
        if not repl_asset.installed_at:
            repl_asset.installed_at = replace_date
        # 교체 장비는 현재 사업으로 자동 등록
        from apps.assets.models import CURRENT_INSTALL_YEAR, CURRENT_INSTALL_PROJECT
        repl_asset.install_year = CURRENT_INSTALL_YEAR
        repl_asset.project_name = CURRENT_INSTALL_PROJECT
        repl_asset.save(update_fields=['status', 'current_school', 'current_center', 'installed_at',
                                       'install_year', 'project_name'])
        AssetHistory.objects.create(
            asset=repl_asset, action='outbound',
            from_location=center.name, to_location=school.name,
            worker=user,
            note=f'현장교체 출고: {outbound.outbound_number} / 교체대상: {faulty_asset.serial_number}'
        )

        # ② 고장 장비: 학교 → 센터 반납
        asset_return = AssetReturn.objects.create(
            return_number=AssetReturn.generate_number(replace_date),
            asset=faulty_asset,
            from_location_type='school',
            from_school=school,
            to_location_type='center',
            to_center=center,
            return_date=replace_date,
            received_by=user,
            reason=reason,
            handover_person=handover_person,
            handover_phone=handover_phone,
            receiver_person=receiver_person,
            receiver_phone=receiver_phone,
            note=f'[현장교체] 교체장비 S/N:{repl_asset.serial_number} 설치 / {note}',
        )
        faulty_asset.status = 'center'
        faulty_asset.current_center = center
        faulty_asset.current_school = None
        faulty_asset.save(update_fields=['status', 'current_center', 'current_school'])
        AssetHistory.objects.create(
            asset=faulty_asset, action='replace',
            from_location=school.name, to_location=center.name,
            worker=user,
            note=f'현장교체 반납: {asset_return.return_number} / 교체장비: {repl_asset.serial_number} / 사유: {reason}'
        )

        return Response({
            'message': f'현장 교체 완료: {school.name}',
            'outbound': AssetOutboundSerializer(outbound).data,
            'return':   AssetReturnSerializer(asset_return).data,
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['patch'], permission_classes=[permissions.IsAuthenticated])
    def center_outbound_update(self, request, pk=None):
        """센터 출고 수정 (일반사용자: 본인 출고만)"""
        user = request.user
        try:
            outbound = AssetOutbound.objects.get(pk=pk)
        except AssetOutbound.DoesNotExist:
            return Response({'error': '출고 기록 없음'}, status=status.HTTP_404_NOT_FOUND)
        if user.role not in ('superadmin', 'admin'):
            if outbound.from_location_type != 'center' or outbound.issued_by_id != user.id:
                return Response({'error': '수정 권한 없음'}, status=status.HTTP_403_FORBIDDEN)
        for field in ('outbound_date', 'handover_person', 'receiver_person', 'note'):
            if field in request.data:
                setattr(outbound, field, request.data[field])
        outbound.save()
        return Response(AssetOutboundSerializer(outbound).data)

    @action(detail=True, methods=['delete'], permission_classes=[permissions.IsAuthenticated])
    def center_outbound_delete(self, request, pk=None):
        """센터 출고 삭제 (일반사용자: 본인 출고만, 재고 복구)"""
        user = request.user
        try:
            outbound = AssetOutbound.objects.select_related('asset').get(pk=pk)
        except AssetOutbound.DoesNotExist:
            return Response({'error': '출고 기록 없음'}, status=status.HTTP_404_NOT_FOUND)
        if user.role not in ('superadmin', 'admin'):
            if outbound.from_location_type != 'center' or outbound.issued_by_id != user.id:
                return Response({'error': '삭제 권한 없음'}, status=status.HTTP_403_FORBIDDEN)
        # Asset 상태 복구 (센터로)
        asset = outbound.asset
        asset.status = 'center'
        asset.current_center = outbound.from_center
        asset.current_school = None
        asset.save(update_fields=['status', 'current_center', 'current_school'])
        outbound.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    # ── CSV 일괄 출고 ─────────────────────────
    @action(detail=False, methods=['get'])
    def csv_template(self, request):
        from apps.schools.models import SupportCenter
        response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
        response['Content-Disposition'] = 'attachment; filename="asset_outbound_template.csv"'
        writer = csv.writer(response)
        writer.writerow(['제조번호(S/N)', '출고일', '출고출처(warehouse/center)',
                          '출고센터명', '목적지(center/school/vendor)',
                          '수령센터명', '설치학교명', '인계자', '인수자', '비고'])
        writer.writerow(['SN000001', '2025-02-01', 'warehouse', '',
                          'center', '○○지원센터', '', '홍길동', '김철수', ''])
        centers = SupportCenter.objects.all().order_by('name')
        writer.writerow(['', '', '', '', '', '', '', '', '', '↓ 지원청/센터명 참고'])
        for c in centers:
            writer.writerow(['', '', '', '', '', c.name, '', '', '', ''])
        return response

    @action(detail=False, methods=['post'], permission_classes=[IsAdmin])
    def bulk_import(self, request):
        """출고 일괄 등록 CSV"""
        f = request.FILES.get('file')
        if not f:
            return Response({'error': 'CSV 파일을 첨부해 주세요.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            decoded = f.read().decode('utf-8-sig')
        except UnicodeDecodeError:
            decoded = f.read().decode('cp949', errors='replace')

        from apps.schools.models import SupportCenter, School
        from django.utils import timezone as tz
        reader = csv.DictReader(io.StringIO(decoded))
        created, errors = 0, []

        for row_num, row in enumerate(reader, start=2):
            try:
                sn = (row.get('제조번호(S/N)') or row.get('제조번호') or '').strip()
                if not sn:
                    continue
                try:
                    asset = Asset.objects.get(serial_number=sn)
                except Asset.DoesNotExist:
                    errors.append(f'{row_num}행: S/N [{sn}] 없음')
                    continue

                date_str = (row.get('출고일') or '').strip()
                outbound_date = dt_date.fromisoformat(date_str) if date_str else tz.localdate()

                from_type   = (row.get('출고출처(warehouse/center)') or 'warehouse').strip()
                from_center = None
                fc_name = (row.get('출고센터명') or '').strip()
                if from_type == 'center' and fc_name:
                    from_center = SupportCenter.objects.filter(name=fc_name).first()

                to_type    = (row.get('목적지(center/school/vendor)') or 'center').strip()
                to_center  = None
                to_school  = None
                tc_name    = (row.get('수령센터명') or '').strip()
                ts_name    = (row.get('설치학교명') or '').strip()
                if to_type == 'center' and tc_name:
                    to_center = SupportCenter.objects.filter(name=tc_name).first()
                elif to_type == 'school' and ts_name:
                    to_school = School.objects.filter(name=ts_name).first()

                outbound = AssetOutbound.objects.create(
                    outbound_number=AssetOutbound.generate_number(outbound_date),
                    asset=asset,
                    from_location_type=from_type,
                    from_center=from_center,
                    to_location_type=to_type,
                    to_center=to_center,
                    to_school=to_school,
                    outbound_date=outbound_date,
                    issued_by=request.user,
                    handover_person=(row.get('인계자') or '').strip(),
                    receiver_person=(row.get('인수자') or '').strip(),
                    note=(row.get('비고') or '').strip(),
                )
                # Asset 상태 변경
                if to_type == 'center' and to_center:
                    asset.status = 'center'
                    asset.current_center = to_center
                    asset.current_school = None
                elif to_type == 'school' and to_school:
                    asset.status = 'installed'
                    asset.current_school = to_school
                    if not asset.installed_at:
                        asset.installed_at = outbound_date
                elif to_type == 'vendor':
                    asset.status = 'rma'
                asset.save(update_fields=['status', 'current_center', 'current_school', 'installed_at'])
                AssetHistory.objects.create(
                    asset=asset, action='outbound' if to_type != 'vendor' else 'rma_send',
                    from_location=from_center.name if from_center else '창고',
                    to_location=(to_center.name if to_center else
                                  to_school.name if to_school else '제조사'),
                    worker=request.user,
                    note=f'CSV 일괄 출고: {outbound.outbound_number}'
                )
                created += 1
            except Exception as e:
                errors.append(f'{row_num}행: {e}')

        return Response({'created': created, 'errors': errors})

    # ── PDF 생성/다운로드/서명 ────────────────
    @action(detail=True, methods=['post'])
    def generate_pdf(self, request, pk=None):
        from .services import generate_outbound_pdf
        try:
            rel_path = generate_outbound_pdf(self.get_object().id)
            return Response({'pdf_path': rel_path, 'url': f'{settings.MEDIA_URL}{rel_path}'})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['get'])
    def download_pdf(self, request, pk=None):
        from .services import generate_outbound_pdf
        outbound = self.get_object()
        if not outbound.pdf_path:
            generate_outbound_pdf(outbound.id)
            outbound.refresh_from_db()
        abs_path = os.path.join(settings.MEDIA_ROOT, outbound.pdf_path)
        if not os.path.exists(abs_path):
            raise Http404
        return FileResponse(
            open(abs_path, 'rb'), content_type='application/pdf',
            as_attachment=True, filename=f'장비출고증_{outbound.outbound_number}.pdf'
        )

    @action(detail=True, methods=['post'])
    def sign(self, request, pk=None):
        outbound = self.get_object()
        fields   = []
        for field in ('handover_signature', 'receiver_signature',
                       'handover_person', 'handover_phone',
                       'receiver_person', 'receiver_phone'):
            val = request.data.get(field, '')
            if val:
                setattr(outbound, field, val)
                fields.append(field)
        if not fields:
            return Response({'error': '저장할 데이터가 없습니다.'}, status=status.HTTP_400_BAD_REQUEST)
        outbound.save(update_fields=fields)
        return Response({'message': '서명 저장 완료'})


# ─────────────────────────────────────
# AssetReturn (장비 반납/회수)
# ─────────────────────────────────────

class AssetReturnViewSet(NoPaginateMixin, viewsets.ModelViewSet):
    queryset = AssetReturn.objects.select_related(
        'asset', 'asset__asset_model', 'asset__asset_model__category',
        'from_school', 'from_center', 'to_center', 'received_by',
    ).order_by('-return_date', '-created_at')
    serializer_class = AssetReturnSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        p  = self.request.query_params
        q       = p.get('q')
        center  = p.get('center')
        school  = p.get('school')
        user    = self.request.user

        if q:
            qs = qs.filter(
                Q(asset__serial_number__icontains=q) |
                Q(return_number__icontains=q)
            )
        if center:
            qs = qs.filter(to_center_id=center)
        if school:
            qs = qs.filter(from_school_id=school)
        # 일반사용자: 본인 센터 반납만
        if user.role not in ('superadmin', 'admin'):
            if not getattr(user, 'support_center_id', None):
                return qs.none()
            qs = qs.filter(to_center_id=user.support_center_id)
        return qs

    def perform_create(self, serializer):
        from rest_framework.exceptions import ValidationError
        user = self.request.user
        if user.role not in ('superadmin', 'admin'):
            if not getattr(user, 'support_center_id', None):
                raise ValidationError('소속 지원청이 없어 반납을 등록할 수 없습니다.')
            serializer.save(
                received_by=user,
                to_center_id=user.support_center_id,
                to_location_type='center',
            )
        else:
            serializer.save(received_by=user)

    # ── PDF 생성/다운로드/서명 ────────────────
    @action(detail=True, methods=['post'])
    def generate_pdf(self, request, pk=None):
        from .services import generate_return_pdf
        try:
            rel_path = generate_return_pdf(self.get_object().id)
            return Response({'pdf_path': rel_path, 'url': f'{settings.MEDIA_URL}{rel_path}'})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['get'])
    def download_pdf(self, request, pk=None):
        from .services import generate_return_pdf
        ret = self.get_object()
        if not ret.pdf_path:
            generate_return_pdf(ret.id)
            ret.refresh_from_db()
        abs_path = os.path.join(settings.MEDIA_ROOT, ret.pdf_path)
        if not os.path.exists(abs_path):
            raise Http404
        return FileResponse(
            open(abs_path, 'rb'), content_type='application/pdf',
            as_attachment=True, filename=f'장비반납증_{ret.return_number}.pdf'
        )

    @action(detail=True, methods=['post'])
    def sign(self, request, pk=None):
        ret    = self.get_object()
        fields = []
        for field in ('handover_signature', 'receiver_signature',
                       'handover_person', 'handover_phone',
                       'receiver_person', 'receiver_phone'):
            val = request.data.get(field, '')
            if val:
                setattr(ret, field, val)
                fields.append(field)
        if not fields:
            return Response({'error': '저장할 데이터가 없습니다.'}, status=status.HTTP_400_BAD_REQUEST)
        ret.save(update_fields=fields)
        return Response({'message': '서명 저장 완료'})


# ─────────────────────────────────────
# AssetRMA (RMA 관리)
# ─────────────────────────────────────

class AssetRMAViewSet(NoPaginateMixin, viewsets.ModelViewSet):
    queryset = AssetRMA.objects.select_related(
        'asset', 'asset__asset_model',
        'replacement_asset', 'handled_by',
    ).order_by('-created_at')
    serializer_class = AssetRMASerializer
    permission_classes = [IsAdmin]

    def get_queryset(self):
        qs = super().get_queryset()
        p  = self.request.query_params
        q       = p.get('q')
        stat    = p.get('status')
        if q:
            qs = qs.filter(
                Q(asset__serial_number__icontains=q) |
                Q(rma_number__icontains=q) |
                Q(new_serial__icontains=q)
            )
        if stat:
            qs = qs.filter(status=stat)
        return qs

    @transaction.atomic
    @action(detail=True, methods=['post'])
    def complete_rma(self, request, pk=None):
        """
        RMA 완료 처리 트랜잭션
        - 동일 S/N 반환: 기존 Asset 창고 입고
        - S/N 변경(수리불가 교체): 기존 폐기 + 신규 Asset 생성 (특별관리)
        """
        from django.utils import timezone as tz
        rma = self.get_object()
        new_serial  = (request.data.get('new_serial') or '').strip()
        rma_number  = (request.data.get('rma_number') or rma.rma_number or '').strip()
        returned_date_str = (request.data.get('returned_date') or '').strip()
        returned_date = dt_date.fromisoformat(returned_date_str) if returned_date_str else tz.localdate()
        note        = (request.data.get('note') or '').strip()

        original_asset = rma.asset

        if not new_serial or new_serial == original_asset.serial_number:
            # ── 동일 S/N 반환 (수리 완료) ───────────────
            original_asset.status = 'warehouse'
            original_asset.current_center = None
            original_asset.current_school = None
            original_asset.save(update_fields=['status', 'current_center', 'current_school'])

            rma.status        = 'returned'
            rma.returned_date = returned_date
            rma.rma_number    = rma_number
            rma.note          = note
            rma.save(update_fields=['status', 'returned_date', 'rma_number', 'note'])

            # 입고 기록
            AssetInbound.objects.create(
                inbound_number=AssetInbound.generate_number(returned_date),
                asset=original_asset,
                from_location_type='vendor',
                from_location_name='제조사(RMA 수리 반환)',
                to_location_type='warehouse',
                inbound_date=returned_date,
                received_by=request.user,
                note=f'RMA 완료(수리) — RMA번호: {rma_number}'
            )
            AssetHistory.objects.create(
                asset=original_asset, action='rma_return',
                from_location='제조사', to_location='창고',
                worker=request.user,
                note=f'RMA 수리 반환 — RMA번호: {rma_number}'
            )
            return Response({
                'result': 'same_sn',
                'message': f'RMA 수리 완료 — S/N {original_asset.serial_number} 창고 입고 처리',
                'asset_id': original_asset.id,
            })

        else:
            # ── S/N 변경 교체품 (수리불가) ──────────────
            # 기존 Asset 폐기
            from django.utils import timezone
            original_asset.status     = 'disposed'
            original_asset.disposed_at = returned_date
            original_asset.save(update_fields=['status', 'disposed_at'])
            AssetHistory.objects.create(
                asset=original_asset, action='dispose',
                from_location='RMA 발송', to_location='폐기',
                worker=request.user,
                note=f'RMA 수리불가 폐기 — 교체품 S/N: {new_serial}'
            )

            # 신규 Asset 생성 (교체품 — 특별관리)
            new_asset = Asset.objects.create(
                serial_number=new_serial,
                asset_model=original_asset.asset_model,
                status='warehouse',
                is_rma_replaced=True,
                replaced_from=original_asset,
                purchased_at=original_asset.purchased_at,
                note=f'RMA 교체품 (원본 S/N: {original_asset.serial_number})',
            )

            # RMA 업데이트
            rma.status            = 'replaced'
            rma.new_serial        = new_serial
            rma.replacement_asset = new_asset
            rma.returned_date     = returned_date
            rma.rma_number        = rma_number
            rma.note              = note
            rma.save(update_fields=[
                'status', 'new_serial', 'replacement_asset',
                'returned_date', 'rma_number', 'note'
            ])

            # 입고 기록 (교체품 창고 입고)
            AssetInbound.objects.create(
                inbound_number=AssetInbound.generate_number(returned_date),
                asset=new_asset,
                from_location_type='vendor',
                from_location_name='제조사(RMA 교체품)',
                to_location_type='warehouse',
                inbound_date=returned_date,
                received_by=request.user,
                note=f'RMA 교체품 수령 — 원본 S/N: {original_asset.serial_number} / RMA번호: {rma_number}'
            )
            AssetHistory.objects.create(
                asset=new_asset, action='rma_replaced',
                from_location='제조사(교체품)', to_location='창고',
                worker=request.user,
                note=f'RMA 교체품 수령 — 원본 S/N: {original_asset.serial_number}'
            )
            return Response({
                'result': 'replaced',
                'message': f'RMA 교체품 수령 — 원본 {original_asset.serial_number} 폐기 / 신규 {new_serial} 창고 입고',
                'original_asset_id': original_asset.id,
                'new_asset_id': new_asset.id,
                'is_rma_replaced': True,
            })


# ─────────────────────────────────────
# DeviceNetworkConfig (장비별 네트워크 설정)
# ─────────────────────────────────────

class DeviceNetworkConfigViewSet(viewsets.ModelViewSet):
    queryset = DeviceNetworkConfig.objects.select_related(
        'asset', 'asset__asset_model'
    )
    serializer_class = DeviceNetworkConfigSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        asset_id = self.request.query_params.get('asset_id')
        if asset_id:
            qs = qs.filter(asset_id=asset_id)
        return qs

    @action(detail=False, methods=['get', 'put', 'patch'])
    def by_asset(self, request):
        """GET/PUT/PATCH /asset_configs/by_asset/?asset_id=X"""
        asset_id = request.query_params.get('asset_id')
        if not asset_id:
            return Response({'error': 'asset_id 파라미터 필요'}, status=status.HTTP_400_BAD_REQUEST)
        config, _ = DeviceNetworkConfig.objects.get_or_create(asset_id=asset_id)
        if request.method == 'GET':
            return Response(DeviceNetworkConfigSerializer(config).data)
        serializer = DeviceNetworkConfigSerializer(config, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


# ─────────────────────────────────────
# AssetModelConfig (모델별 표준 설정 — 장비 설정 탭)
# ─────────────────────────────────────

class AssetModelConfigViewSet(viewsets.ModelViewSet):
    queryset = AssetModelConfig.objects.select_related(
        'asset_model', 'asset_model__category', 'updated_by'
    )
    serializer_class = AssetModelConfigSerializer
    permission_classes = [IsAdmin]

    def perform_create(self, serializer):
        serializer.save(updated_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    @action(detail=True, methods=['post'])
    def apply_to_assets(self, request, pk=None):
        """
        이 모델 설정을 해당 모델의 모든 장비 DeviceNetworkConfig에 일괄 적용
        우선 C3100-24TL 등 단일 모델 기반 적용
        """
        config  = self.get_object()
        assets  = Asset.objects.filter(asset_model=config.asset_model)
        updated = 0
        for asset in assets:
            dc, _ = DeviceNetworkConfig.objects.get_or_create(asset=asset)
            dc.vlan_mgmt      = config.vlan_mgmt
            dc.vlan_data      = config.vlan_data
            dc.uplink_port    = config.uplink_port
            dc.uplink_speed   = config.uplink_speed
            dc.ssh_enabled    = config.ssh_enabled
            dc.snmp_community = config.snmp_community
            dc.firmware_ver   = config.firmware_ver
            dc.config_note    = f'모델 표준 설정 적용 ({config.asset_model.model_name})'
            dc.save()
            updated += 1
        return Response({
            'message': f'{config.asset_model.model_name} 모델 {updated}대 설정 적용 완료',
            'updated': updated,
        })

    @action(detail=False, methods=['get'])
    def by_model(self, request):
        """GET /model_configs/by_model/?model_id=X"""
        model_id = request.query_params.get('model_id')
        if not model_id:
            return Response({'error': 'model_id 파라미터 필요'}, status=status.HTTP_400_BAD_REQUEST)
        config, _ = AssetModelConfig.objects.get_or_create(asset_model_id=model_id)
        return Response(AssetModelConfigSerializer(config).data)
