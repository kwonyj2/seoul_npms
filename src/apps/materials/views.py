from django.shortcuts import render
from django.db.models import Q
from django.http import FileResponse, Http404, HttpResponse
from django.contrib.auth.decorators import login_required
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.conf import settings
import os, csv, io
from .models import (MaterialCategory, Material, WarehouseInventory,
                     CenterInventory, MaterialInbound, MaterialOutbound,
                     MaterialReturn, MaterialUsage)
from .serializers import (MaterialCategorySerializer, MaterialSerializer,
                           WarehouseInventorySerializer, CenterInventorySerializer,
                           MaterialInboundSerializer, MaterialOutboundSerializer,
                           MaterialReturnSerializer, MaterialUsageSerializer)
from core.permissions.roles import IsAdmin


@login_required
def materials_view(request):
    return render(request, 'materials/index.html')


class NoPaginateMixin:
    """?no_page=1 파라미터 시 페이지네이션 없이 전체 결과 반환 (Excel 다운로드용)"""
    def paginate_queryset(self, queryset):
        if self.request.query_params.get('no_page'):
            return None
        return super().paginate_queryset(queryset)


class MaterialCategoryViewSet(viewsets.ModelViewSet):
    queryset = MaterialCategory.objects.filter(is_active=True)
    serializer_class = MaterialCategorySerializer
    permission_classes = [permissions.IsAuthenticated]


class MaterialViewSet(NoPaginateMixin, viewsets.ModelViewSet):
    queryset = Material.objects.select_related('category').filter(is_active=True)
    serializer_class = MaterialSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        q   = self.request.query_params.get('q')
        cat = self.request.query_params.get('category')
        if q:
            qs = qs.filter(name__icontains=q)
        if cat:
            qs = qs.filter(category_id=cat)
        # resident: 본인 지원청에 재고가 있는 품목만
        user = self.request.user
        if user.role == 'resident' and user.support_center_id:
            mat_ids = CenterInventory.objects.filter(
                support_center_id=user.support_center_id
            ).values_list('material_id', flat=True)
            qs = qs.filter(id__in=mat_ids)
        return qs

    @action(detail=False, methods=['get'])
    def csv_template(self, request):
        """CSV 양식 다운로드"""
        response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
        response['Content-Disposition'] = 'attachment; filename="material_template.csv"'
        writer = csv.writer(response)
        writer.writerow(['분류코드', '자재코드', '자재명', '규격', '단위', '최소재고', '공급업체', '비고'])
        writer.writerow(['cable',     'CAB-UTP-001', 'UTP CAT6 케이블', '305m Roll', 'roll', '5', '한국정보통신', ''])
        writer.writerow(['connector', 'CON-RJ45-001', 'RJ45 커넥터',    '8P8C',      'ea',   '50', '',            ''])
        writer.writerow(['equipment', 'EQP-SW-001',   '스위치 24포트',  'GS324T',    'ea',   '2',  '넷기어',      ''])
        return response

    @action(detail=False, methods=['post'], permission_classes=[IsAdmin])
    def bulk_import(self, request):
        """CSV 일괄 등록"""
        f = request.FILES.get('file')
        if not f:
            return Response({'error': 'CSV 파일을 첨부해 주세요.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            decoded = f.read().decode('utf-8-sig')
        except UnicodeDecodeError:
            decoded = f.read().decode('cp949', errors='replace')

        UNIT_MAP = {
            'ea': 'ea', '개': 'ea', 'm': 'm', '미터': 'm',
            'roll': 'roll', '롤': 'roll', 'set': 'set', '세트': 'set',
            'box': 'box', '박스': 'box',
        }
        VALID_CATS = dict(MaterialCategory.CATEGORY_CHOICES)

        reader = csv.DictReader(io.StringIO(decoded))
        created, updated, errors = 0, 0, []

        for row_num, row in enumerate(reader, start=2):
            try:
                cat_code = (row.get('분류코드') or '').strip()
                mat_code = (row.get('자재코드') or '').strip()
                mat_name = (row.get('자재명')   or '').strip()
                if not mat_code or not mat_name:
                    errors.append(f'{row_num}행: 자재코드/자재명 필수')
                    continue

                cat, _ = MaterialCategory.objects.get_or_create(
                    code=cat_code or 'other',
                    defaults={
                        'name':      VALID_CATS.get(cat_code, cat_code or '기타'),
                        'type_code': cat_code if cat_code in VALID_CATS else 'other',
                    }
                )

                _, is_new = Material.objects.update_or_create(
                    code=mat_code,
                    defaults={
                        'category':  cat,
                        'name':      mat_name,
                        'spec':      (row.get('규격')     or '').strip(),
                        'unit':      UNIT_MAP.get((row.get('단위') or 'ea').strip().lower(), 'ea'),
                        'min_stock': int(row.get('최소재고') or 0),
                        'supplier':  (row.get('공급업체') or '').strip(),
                        'note':      (row.get('비고')     or '').strip(),
                        'is_active': True,
                    }
                )
                if is_new:
                    created += 1
                else:
                    updated += 1
            except Exception as e:
                errors.append(f'{row_num}행: {e}')

        return Response({'created': created, 'updated': updated, 'errors': errors})


class WarehouseInventoryViewSet(NoPaginateMixin, viewsets.ModelViewSet):
    queryset = WarehouseInventory.objects.select_related('material', 'material__category').order_by('material__category__order', 'material__name')
    serializer_class = WarehouseInventorySerializer
    permission_classes = [IsAdmin]

    def get_queryset(self):
        qs = super().get_queryset()
        q        = self.request.query_params.get('q')
        category = self.request.query_params.get('category')
        if q:
            qs = qs.filter(material__name__icontains=q)
        if category:
            qs = qs.filter(material__category_id=category)
        return qs

    @action(detail=False, methods=['get'])
    def low_stock(self, request):
        from django.db.models import F
        low  = self.get_queryset().filter(quantity__lte=F('material__min_stock'))
        page = self.paginate_queryset(low)
        if page is not None:
            return self.get_paginated_response(WarehouseInventorySerializer(page, many=True).data)
        return Response(WarehouseInventorySerializer(low, many=True).data)


class CenterInventoryViewSet(NoPaginateMixin, viewsets.ModelViewSet):
    queryset = CenterInventory.objects.select_related('support_center', 'material', 'material__category')
    serializer_class = CenterInventorySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.role not in ('superadmin', 'admin'):
            if not user.support_center_id:
                return qs.none()
            return qs.filter(support_center_id=user.support_center_id).order_by(
                'material__category__order', 'material__name'
            )
        center   = self.request.query_params.get('center')
        q        = self.request.query_params.get('q')
        category = self.request.query_params.get('category')
        if center:
            qs = qs.filter(support_center__code=center)
        if q:
            qs = qs.filter(material__name__icontains=q)
        if category:
            qs = qs.filter(material__category_id=category)
        return qs.order_by('support_center__id', 'material__category__order', 'material__name')


class MaterialInboundViewSet(NoPaginateMixin, viewsets.ModelViewSet):
    queryset = MaterialInbound.objects.select_related('material', 'material__category', 'received_by').order_by('-inbound_date')
    serializer_class = MaterialInboundSerializer
    permission_classes = [IsAdmin]

    def get_queryset(self):
        qs = super().get_queryset()
        q        = self.request.query_params.get('q')
        category = self.request.query_params.get('category')
        if q:
            qs = qs.filter(material__name__icontains=q)
        if category:
            qs = qs.filter(material__category_id=category)
        return qs

    def perform_create(self, serializer):
        serializer.save(received_by=self.request.user)

    def perform_destroy(self, instance):
        """입고 삭제 시 창고 재고 차감"""
        inv = WarehouseInventory.objects.filter(material=instance.material).first()
        if inv:
            inv.quantity = max(0, inv.quantity - instance.quantity)
            inv.save()
        instance.delete()

    @action(detail=False, methods=['get'])
    def csv_template(self, request):
        """입고 일괄 등록 CSV 양식 다운로드 (헤더만 — 예시 행 없음)"""
        response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
        response['Content-Disposition'] = 'attachment; filename="inbound_template.csv"'
        writer = csv.writer(response)
        writer.writerow(['자재코드', '수량', '입고일', '공급업체', '인계자', '인수자', '비고'])
        return response

    @action(detail=False, methods=['post'])
    def bulk_import(self, request):
        """입고 일괄 등록 CSV"""
        f = request.FILES.get('file')
        if not f:
            return Response({'error': 'CSV 파일을 첨부해 주세요.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            decoded = f.read().decode('utf-8-sig')
        except UnicodeDecodeError:
            decoded = f.read().decode('cp949', errors='replace')

        from django.utils import timezone as tz
        reader = csv.DictReader(io.StringIO(decoded))
        created, errors = 0, []

        for row_num, row in enumerate(reader, start=2):
            try:
                mat_code = (row.get('자재코드') or '').strip()
                qty_str  = (row.get('수량')     or '').strip()
                if not mat_code or not qty_str:
                    errors.append(f'{row_num}행: 자재코드/수량 필수')
                    continue

                try:
                    material = Material.objects.get(code=mat_code)
                except Material.DoesNotExist:
                    errors.append(f'{row_num}행: 자재코드 [{mat_code}] 없음 — 품목 등록 먼저 필요')
                    continue

                qty = int(qty_str)
                if qty <= 0:
                    errors.append(f'{row_num}행: 수량은 1 이상이어야 합니다')
                    continue

                date_str = (row.get('입고일') or '').strip()
                try:
                    from datetime import date
                    inbound_date = date.fromisoformat(date_str) if date_str else tz.localdate()
                except ValueError:
                    errors.append(f'{row_num}행: 입고일 형식 오류 (YYYY-MM-DD)')
                    continue

                inbound = MaterialInbound.objects.create(
                    inbound_number=MaterialInbound.generate_number(inbound_date),
                    material=material,
                    quantity=qty,
                    unit_price=0,
                    supplier=(row.get('공급업체')  or '').strip(),
                    handover_person=(row.get('인계자') or '').strip(),
                    receiver_person=(row.get('인수자') or '').strip(),
                    inbound_date=inbound_date,
                    received_by=request.user,
                    note=(row.get('비고') or '').strip(),
                )
                # 창고 재고 증가
                inv, _ = WarehouseInventory.objects.get_or_create(
                    material=material, defaults={'quantity': 0}
                )
                inv.quantity += qty
                inv.save()
                created += 1
            except Exception as e:
                errors.append(f'{row_num}행: {e}')

        return Response({'created': created, 'errors': errors})

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
        return FileResponse(open(abs_path, 'rb'), content_type='application/pdf',
                            as_attachment=True, filename=f'입고증_{inbound.inbound_number}.pdf')

    @action(detail=True, methods=['post'])
    def sign(self, request, pk=None):
        inbound  = self.get_object()
        fields   = []
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


class MaterialOutboundViewSet(NoPaginateMixin, viewsets.ModelViewSet):
    queryset = MaterialOutbound.objects.select_related(
        'material', 'material__category', 'to_center', 'to_worker',
        'issued_by', 'issued_by__support_center'
    ).order_by('-outbound_date')
    serializer_class = MaterialOutboundSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_permissions(self):
        if self.action in ('create', 'update', 'partial_update', 'destroy'):
            return [IsAdmin()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        qs = super().get_queryset()
        user      = self.request.user
        q         = self.request.query_params.get('q')
        category  = self.request.query_params.get('category')
        to_center   = self.request.query_params.get('to_center')
        from_center = self.request.query_params.get('from_center')
        fw_param    = self.request.query_params.get('from_warehouse')
        if q:
            qs = qs.filter(material__name__icontains=q)
        if category:
            qs = qs.filter(material__category_id=category)
        if to_center:
            qs = qs.filter(to_center_id=to_center)
        if from_center:
            qs = qs.filter(
                Q(issued_by__support_center_id=from_center) |
                Q(from_center_id=from_center)
            )
        if user.role not in ('superadmin', 'admin'):
            if not user.support_center_id:
                return qs.none()
            if fw_param == 'false':
                qs = qs.filter(
                    Q(issued_by=user, from_warehouse=False) |
                    Q(from_center_id=user.support_center_id, from_warehouse=False)
                )
            else:
                qs = qs.filter(to_center_id=user.support_center_id, from_warehouse=True)
        elif fw_param is not None:
            qs = qs.filter(from_warehouse=(fw_param.lower() not in ('false', '0')))
        return qs

    def perform_create(self, serializer):
        serializer.save(issued_by=self.request.user)

    def perform_destroy(self, instance):
        """출고 삭제 시 창고 재고 복구, 센터 재고 차감"""
        inv = WarehouseInventory.objects.filter(material=instance.material).first()
        if inv:
            inv.quantity += instance.quantity
            inv.save()
        if instance.to_center:
            cinv = CenterInventory.objects.filter(
                support_center=instance.to_center, material=instance.material
            ).first()
            if cinv:
                cinv.quantity = max(0, cinv.quantity - instance.quantity)
                cinv.save()
        instance.delete()

    @action(detail=False, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def center_outbound(self, request):
        """센터에서 현장/기사로 출고 (resident용)"""
        from django.utils import timezone as tz
        from datetime import date as dt_date
        user = request.user
        if not user.support_center_id:
            return Response({'error': '소속 지원청이 없습니다'}, status=status.HTTP_400_BAD_REQUEST)

        material_id = request.data.get('material')
        qty_raw     = request.data.get('quantity')
        if not material_id or not qty_raw:
            return Response({'error': '품목·수량 필수'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            material = Material.objects.get(id=material_id)
            qty = int(qty_raw)
            assert qty > 0
        except (Material.DoesNotExist, ValueError, AssertionError):
            return Response({'error': '품목 또는 수량 오류'}, status=status.HTTP_400_BAD_REQUEST)

        date_str = (request.data.get('outbound_date') or '').strip()
        try:
            outbound_date = dt_date.fromisoformat(date_str) if date_str else tz.localdate()
        except ValueError:
            return Response({'error': '출고일 형식 오류 (YYYY-MM-DD)'}, status=status.HTTP_400_BAD_REQUEST)

        day_key = tz.now().strftime('%Y%m%d')
        seq = MaterialOutbound.objects.filter(
            outbound_number__startswith=f'OUT{day_key}'
        ).count() + 1

        # 센터 재고 부족 검증
        try:
            cinv = CenterInventory.objects.get(
                support_center_id=user.support_center_id, material=material
            )
            if cinv.quantity < qty:
                return Response(
                    {'error': f'센터 재고 부족: 현재 {cinv.quantity}, 요청 {qty}'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except CenterInventory.DoesNotExist:
            return Response(
                {'error': f'[{material.name}] 센터 재고 없음'},
                status=status.HTTP_400_BAD_REQUEST
            )

        outbound = MaterialOutbound.objects.create(
            outbound_number   = f'OUT{day_key}_{seq:03d}',
            material          = material,
            quantity          = qty,
            from_warehouse    = False,
            to_worker_id      = request.data.get('to_worker') or None,
            to_school         = (request.data.get('to_school') or '').strip(),
            outbound_date     = outbound_date,
            issued_by         = user,
            handover_person   = (request.data.get('handover_person') or '').strip(),
            receiver_person   = (request.data.get('receiver_person') or '').strip(),
            note              = (request.data.get('note') or '').strip(),
        )
        # 센터 재고 감소 (검증 통과 후)
        cinv.quantity -= qty
        cinv.save()

        return Response(MaterialOutboundSerializer(outbound).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['patch'], permission_classes=[permissions.IsAuthenticated])
    def center_outbound_update(self, request, pk=None):
        """센터 출고 수정 (resident용) — from_warehouse=False"""
        user = request.user
        try:
            outbound = MaterialOutbound.objects.get(pk=pk)
        except MaterialOutbound.DoesNotExist:
            return Response({'error': '해당 출고 기록 없음'}, status=status.HTTP_404_NOT_FOUND)
        if user.role not in ('superadmin', 'admin'):
            if outbound.from_warehouse or outbound.issued_by_id != user.id:
                return Response({'error': '수정 권한 없음'}, status=status.HTTP_403_FORBIDDEN)
        old_qty = outbound.quantity
        new_qty = int(request.data.get('quantity', old_qty))
        diff = new_qty - old_qty
        center_id = user.support_center_id or (outbound.issued_by.support_center_id if outbound.issued_by else None)
        if diff > 0 and center_id:
            cinv = CenterInventory.objects.filter(
                support_center_id=center_id, material=outbound.material
            ).first()
            if not cinv or cinv.quantity < diff:
                return Response({'error': '센터 재고 부족'}, status=status.HTTP_400_BAD_REQUEST)
        for field in ('quantity', 'outbound_date', 'to_school', 'handover_person',
                      'receiver_person', 'note'):
            if field in request.data:
                val = request.data[field]
                if field == 'quantity':
                    val = int(val)
                setattr(outbound, field, val)
        outbound.save()
        if diff != 0 and center_id:
            cinv, _ = CenterInventory.objects.get_or_create(
                support_center_id=center_id, material=outbound.material,
                defaults={'quantity': 0}
            )
            cinv.quantity = max(0, cinv.quantity - diff)
            cinv.save()
        return Response(MaterialOutboundSerializer(outbound).data)

    @action(detail=True, methods=['delete'], permission_classes=[permissions.IsAuthenticated])
    def center_outbound_delete(self, request, pk=None):
        """센터 출고 삭제 (resident용) — from_warehouse=False"""
        user = request.user
        try:
            outbound = MaterialOutbound.objects.get(pk=pk)
        except MaterialOutbound.DoesNotExist:
            return Response({'error': '해당 출고 기록 없음'}, status=status.HTTP_404_NOT_FOUND)
        if user.role not in ('superadmin', 'admin'):
            if outbound.from_warehouse or outbound.issued_by_id != user.id:
                return Response({'error': '삭제 권한 없음'}, status=status.HTTP_403_FORBIDDEN)
        center_id = user.support_center_id or (outbound.issued_by.support_center_id if outbound.issued_by else None)
        if center_id:
            cinv = CenterInventory.objects.filter(
                support_center_id=center_id, material=outbound.material
            ).first()
            if cinv:
                cinv.quantity += outbound.quantity
                cinv.save()
        outbound.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=['get'])
    def csv_template(self, request):
        """출고 일괄 등록 CSV 양식 다운로드"""
        from apps.schools.models import SupportCenter
        response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
        response['Content-Disposition'] = 'attachment; filename="outbound_template.csv"'
        writer = csv.writer(response)
        writer.writerow(['자재코드', '수량', '출고일', '지원청명', '인계자', '인수자', '비고'])
        # 지원청명 목록을 비고란에 안내 (빈 행이므로 업로드 시 자동 무시됨)
        centers = list(SupportCenter.objects.all().order_by('name'))
        writer.writerow(['', '', '', '', '', '', '↓ 아래 지원청명 참고 (이 행들은 업로드 시 무시됩니다)'])
        for c in centers:
            writer.writerow(['', '', '', c.name, '', '', ''])
        return response

    @action(detail=False, methods=['post'])
    def bulk_import(self, request):
        """출고 일괄 등록 CSV"""
        f = request.FILES.get('file')
        if not f:
            return Response({'error': 'CSV 파일을 첨부해 주세요.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            decoded = f.read().decode('utf-8-sig')
        except UnicodeDecodeError:
            decoded = f.read().decode('cp949', errors='replace')

        from django.utils import timezone as tz
        from apps.schools.models import SupportCenter
        reader = csv.DictReader(io.StringIO(decoded))
        created, errors = 0, []

        for row_num, row in enumerate(reader, start=2):
            try:
                mat_code    = (row.get('자재코드') or '').strip()
                qty_str     = (row.get('수량')     or '').strip()
                # 지원청명 또는 지원청코드 둘 다 허용
                center_val  = (row.get('지원청명') or row.get('지원청코드') or '').strip()
                # 안내용 빈 행 무시
                if not mat_code and not qty_str:
                    continue
                if not mat_code or not qty_str or not center_val:
                    errors.append(f'{row_num}행: 자재코드/수량/지원청명 필수')
                    continue

                try:
                    material = Material.objects.get(code=mat_code)
                except Material.DoesNotExist:
                    errors.append(f'{row_num}행: 자재코드 [{mat_code}] 없음')
                    continue

                try:
                    center = SupportCenter.objects.filter(name=center_val).first() \
                             or SupportCenter.objects.filter(code=center_val).first()
                    if not center:
                        raise SupportCenter.DoesNotExist
                except SupportCenter.DoesNotExist:
                    errors.append(f'{row_num}행: 지원청 [{center_val}] 없음')
                    continue

                qty = int(qty_str)
                if qty <= 0:
                    errors.append(f'{row_num}행: 수량은 1 이상이어야 합니다')
                    continue

                # ── 창고 재고 부족 검증 ──────────────────────────
                try:
                    inv = WarehouseInventory.objects.get(material=material)
                    if inv.quantity < qty:
                        errors.append(
                            f'{row_num}행: [{material.name}] 창고 재고 부족 '
                            f'(현재 {inv.quantity}, 요청 {qty})'
                        )
                        continue
                except WarehouseInventory.DoesNotExist:
                    errors.append(f'{row_num}행: [{material.name}] 창고 재고 없음 (입고 먼저 필요)')
                    continue

                date_str = (row.get('출고일') or '').strip()
                try:
                    from datetime import date
                    outbound_date = date.fromisoformat(date_str) if date_str else tz.localdate()
                except ValueError:
                    errors.append(f'{row_num}행: 출고일 형식 오류 (YYYY-MM-DD)')
                    continue

                date_key = tz.now().strftime('%Y%m%d')
                seq = MaterialOutbound.objects.filter(
                    outbound_number__startswith=f'OUT{date_key}'
                ).count() + 1
                outbound = MaterialOutbound.objects.create(
                    outbound_number=f'OUT{date_key}_{seq:03d}',
                    material=material,
                    quantity=qty,
                    to_center=center,
                    outbound_date=outbound_date,
                    issued_by=request.user,
                    handover_person=(row.get('인계자') or '').strip(),
                    receiver_person=(row.get('인수자') or '').strip(),
                    note=(row.get('비고') or '').strip(),
                )
                # 창고 재고 감소
                inv.quantity -= qty
                inv.save()
                # 지원청 재고 증가
                cinv, _ = CenterInventory.objects.get_or_create(
                    support_center=center, material=material, defaults={'quantity': 0}
                )
                cinv.quantity += qty
                cinv.save()
                created += 1
            except Exception as e:
                errors.append(f'{row_num}행: {e}')

        return Response({'created': created, 'errors': errors})

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
        return FileResponse(open(abs_path, 'rb'), content_type='application/pdf',
                            as_attachment=True, filename=f'출고증_{outbound.outbound_number}.pdf')

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


class MaterialReturnViewSet(NoPaginateMixin, viewsets.ModelViewSet):
    """센터 반납 입고 (현장→센터)"""
    queryset = MaterialReturn.objects.select_related(
        'material', 'material__category', 'to_center', 'from_worker', 'received_by'
    ).order_by('-return_date')
    serializer_class = MaterialReturnSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs   = super().get_queryset()
        user = self.request.user
        q    = self.request.query_params.get('q')
        cat  = self.request.query_params.get('category')
        ctr  = self.request.query_params.get('center')
        if q:
            qs = qs.filter(material__name__icontains=q)
        if cat:
            qs = qs.filter(material__category_id=cat)
        if ctr:
            qs = qs.filter(to_center_id=ctr)
        # 센터 사용자는 본인 센터 반납만 조회
        if user.role not in ('superadmin', 'admin'):
            if not user.support_center_id:
                return qs.none()
            qs = qs.filter(to_center_id=user.support_center_id)
        return qs

    def perform_create(self, serializer):
        from rest_framework.exceptions import ValidationError
        user = self.request.user
        if user.role not in ('superadmin', 'admin'):
            if not user.support_center_id:
                raise ValidationError('소속 지원청이 없어 반납 입고를 등록할 수 없습니다.')
            serializer.save(received_by=user, to_center_id=user.support_center_id)
        else:
            serializer.save(received_by=user)

    def perform_destroy(self, instance):
        """반납 삭제 시 센터 재고 감소"""
        cinv = CenterInventory.objects.filter(
            support_center=instance.to_center, material=instance.material
        ).first()
        if cinv:
            cinv.quantity = max(0, cinv.quantity - instance.quantity)
            cinv.save()
        instance.delete()


class MaterialUsageViewSet(viewsets.ModelViewSet):
    queryset = MaterialUsage.objects.select_related('material', 'school', 'worker').order_by('-used_date')
    serializer_class = MaterialUsageSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        school = self.request.query_params.get('school')
        if school:
            qs = qs.filter(school_id=school)
        return qs
