"""
산출물 통합 조회 API — 모든 서류를 자동 탐지하여 세부 데이터를 표 형태로 제공
새 ReportTemplate 추가 시 자동 인식, PDF 생성 모델도 자동 탐지
"""
import json
from django.apps import apps
from django.http import JsonResponse, HttpResponse
from django.contrib.auth.decorators import login_required
from django.db.models import Q


def _admin_required(view_func):
    from functools import wraps
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'error': '로그인 필요'}, status=401)
        if request.user.role not in ('superadmin', 'admin'):
            return JsonResponse({'error': '권한 없음'}, status=403)
        return view_func(request, *args, **kwargs)
    return _wrapped


def _flatten_nested(prefix, obj):
    """중첩 dict를 평탄화: {'end_point': {'port': '22', 'floor': '3층'}} → {'끝점_포트': '22', '끝점_층': '3층'}"""
    result = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, dict):
                for kk, vv in v.items():
                    result[f'{prefix}_{k}_{kk}'] = vv
            elif isinstance(v, (list,)):
                result[f'{prefix}_{k}'] = ', '.join(str(x) for x in v)
            elif 'signature' in k or 'data:image' in str(v):
                continue  # 서명/이미지 데이터 제외
            else:
                result[f'{prefix}_{k}'] = v
    return result


# ── 자동 탐지: PDF 생성 모델 정의 ──────────────────────
# (pdf_path 필드가 있는 모델을 자동 탐지하되, 표시할 컬럼을 지정)
_PDF_MODEL_CONFIGS = None

def _get_pdf_model_configs():
    """pdf_path 필드 보유 모델 자동 탐지"""
    global _PDF_MODEL_CONFIGS
    if _PDF_MODEL_CONFIGS is not None:
        return _PDF_MODEL_CONFIGS

    ALLOWED_APPS = [
        'incidents', 'assets', 'materials', 'reports', 'education',
    ]
    configs = []
    for app_label in ALLOWED_APPS:
        try:
            app_config = apps.get_app_config(app_label)
        except LookupError:
            continue
        for model in app_config.get_models():
            field_names = [f.name for f in model._meta.get_fields() if hasattr(f, 'column')]
            pdf_field = None
            for fn in field_names:
                if 'pdf' in fn.lower() and 'path' in fn.lower():
                    pdf_field = fn
                    break
            if pdf_field:
                configs.append({
                    'app': app_label,
                    'model_name': model._meta.model_name,
                    'label': str(model._meta.verbose_name),
                    'pdf_field': pdf_field,
                    'model': model,
                })
    _PDF_MODEL_CONFIGS = configs
    return configs


@login_required
@_admin_required
def doc_catalog(request):
    """산출물 카탈로그 — 자동 탐지된 서류 유형 목록"""
    catalog = []

    # 1) Report 템플릿 기반 (JSON data 서류)
    try:
        from apps.reports.models import ReportTemplate, Report
        for tmpl in ReportTemplate.objects.all():
            count = Report.objects.filter(template=tmpl).count()
            catalog.append({
                'id': f'report_{tmpl.id}',
                'type': 'report_template',
                'template_id': tmpl.id,
                'name': tmpl.name,
                'count': count,
                'icon': 'bi-file-earmark-text',
            })
    except Exception:
        pass

    # 2) PDF 생성 모델 기반 (pdf_path 필드)
    for cfg in _get_pdf_model_configs():
        # reports.report는 위에서 처리했으므로 제외
        if cfg['app'] == 'reports' and cfg['model_name'] == 'report':
            continue
        model = cfg['model']
        qs = model.objects.exclude(**{f'{cfg["pdf_field"]}__exact': ''}).exclude(
            **{f'{cfg["pdf_field"]}__isnull': True})
        count = qs.count()
        if count == 0:
            # PDF 없어도 레코드 자체는 표시
            count = model.objects.count()
        catalog.append({
            'id': f'{cfg["app"]}_{cfg["model_name"]}',
            'type': 'pdf_model',
            'app': cfg['app'],
            'model_name': cfg['model_name'],
            'name': cfg['label'],
            'count': count,
            'icon': 'bi-file-earmark-pdf',
        })

    return JsonResponse({'catalog': catalog})


@login_required
@_admin_required
def doc_data(request, doc_id):
    """서류 상세 데이터 — JSON을 펼쳐서 행 단위로 반환"""
    page = max(1, int(request.GET.get('page', 1)))
    page_size = 50
    offset = (page - 1) * page_size
    q = request.GET.get('q', '').strip()

    # Report 템플릿 기반
    if doc_id.startswith('report_'):
        template_id = int(doc_id.replace('report_', ''))
        return _report_template_data(request, template_id, page, page_size, offset, q)

    # PDF 모델 기반
    for cfg in _get_pdf_model_configs():
        if doc_id == f'{cfg["app"]}_{cfg["model_name"]}':
            return _pdf_model_data(request, cfg, page, page_size, offset, q)

    return JsonResponse({'error': '알 수 없는 서류 유형'}, status=404)


# JSON 키 → 한글 라벨 자동 매핑
_LABEL_MAP = {
    # 공통
    'notes': '특이사항', 'doc_type': '문서유형', 'quantity': '수량',
    'install_date': '설치일', 'work_date': '작업일',
    # 장비/스위치
    'floor': '층', 'building': '건물', 'location': '설치장소',
    'model_name': '모델명', 'manufacturer': '제조사', 'serial_number': 'S/N',
    'asset_id': '자산번호', 'category': '분류',
    'network_type': '망종류', 'network_type_label': '망종류명',
    'prev_model': '교체전모델', 'prev_manufacturer': '교체전제조사',
    # 케이블
    'cable_type': '케이블종류', 'cable_length': '케이블길이(m)',
    'work_types': '작업유형', 'work_label': '작업내용',
    'start_point': '시작점', 'end_point': '끝점',
    'port': '포트', 'room': '교실', 'rack': '랙',
    # 기타
    'name': '이름', 'phone': '연락처', 'org': '소속',
    'status': '상태', 'date': '날짜', 'type': '유형',
    'description': '설명', 'detail': '상세', 'reason': '사유',
    'amount': '금액', 'count': '수량', 'unit': '단위',
    'address': '주소', 'code': '코드', 'number': '번호',
}

def _to_label(key):
    """JSON 키를 한글 라벨로 변환"""
    clean = key
    # 전체 키가 매핑에 있으면 바로 반환
    if clean in _LABEL_MAP:
        return _LABEL_MAP[clean]
    # 언더스코어로 분리하여 각 파트를 변환
    parts = clean.split('_')
    # 전체 조합도 체크 (install_date 등)
    for i in range(len(parts), 0, -1):
        combined = '_'.join(parts[:i])
        if combined in _LABEL_MAP:
            rest = parts[i:]
            rest_labels = [_LABEL_MAP.get(p, p) for p in rest]
            return _LABEL_MAP[combined] + (' ' + ' '.join(rest_labels) if rest_labels else '')
    # 개별 파트 변환
    labels = [_LABEL_MAP.get(p, p) for p in parts]
    return ' '.join(labels)


def _report_template_data(request, template_id, page, page_size, offset, q):
    """Report.data JSON을 펼쳐서 반환"""
    from apps.reports.models import Report, ReportTemplate

    try:
        tmpl = ReportTemplate.objects.get(id=template_id)
    except ReportTemplate.DoesNotExist:
        return JsonResponse({'error': '템플릿 없음'}, status=404)

    qs = Report.objects.filter(template=tmpl).select_related('school', 'created_by').order_by('-created_at')
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(school__name__icontains=q))

    # JSON 구조 자동 분석 (첫 레코드에서)
    sample = qs.first()
    array_key = None  # devices, cables 등
    array_fields = []
    top_fields = []

    if sample and sample.data:
        data = sample.data
        for k, v in data.items():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                array_key = k
                # 중첩 dict 펼치기
                for ak, av in v[0].items():
                    if 'signature' in ak or 'photo' in ak.lower() or 'data:image' in str(av):
                        continue
                    if isinstance(av, dict):
                        for akk in av.keys():
                            array_fields.append(f'{ak}_{akk}')
                    else:
                        array_fields.append(ak)
            elif isinstance(v, (str, int, float, bool)) and 'signature' not in k:
                top_fields.append(k)

    # 컬럼 구성: 기본 필드 + JSON top + JSON array
    columns = [
        {'key': '_school', 'label': '학교'},
        {'key': '_status', 'label': '상태'},
    ]
    for tf in top_fields:
        columns.append({'key': f'_top_{tf}', 'label': _to_label(tf)})
    for af in array_fields:
        columns.append({'key': f'_arr_{af}', 'label': _to_label(af)})
    columns.append({'key': '_created', 'label': '생성일'})

    # 데이터 행 생성 (배열은 행으로 펼침)
    all_rows = []
    for report in qs:
        base = {
            '_pk': report.pk,
            '_school': str(report.school) if report.school else '-',
            '_status': report.status,
            '_created': report.created_at.strftime('%Y-%m-%d'),
            '_pdf': report.pdf_path or '',
            '_title': report.title,
        }
        # top-level 필드
        data = report.data or {}
        for tf in top_fields:
            base[f'_top_{tf}'] = data.get(tf, '')

        if array_key and isinstance(data.get(array_key), list):
            for item in data[array_key]:
                row = dict(base)
                for af in array_fields:
                    # 중첩 dict 펼침
                    if '_' in af:
                        parts = af.split('_', 1)
                        parent = item.get(parts[0])
                        if isinstance(parent, dict):
                            row[f'_arr_{af}'] = parent.get(parts[1], '')
                        else:
                            row[f'_arr_{af}'] = item.get(af, '')
                    else:
                        val = item.get(af, '')
                        if isinstance(val, list):
                            val = ', '.join(str(x) for x in val)
                        row[f'_arr_{af}'] = val
                all_rows.append(row)
        else:
            all_rows.append(base)

    # 검색 필터 (펼친 데이터에서)
    if q:
        q_lower = q.lower()
        all_rows = [r for r in all_rows if any(q_lower in str(v).lower() for v in r.values())]

    total = len(all_rows)
    rows = all_rows[offset:offset + page_size]

    return JsonResponse({
        'name': tmpl.name,
        'columns': columns,
        'rows': rows,
        'total': total,
        'page': page,
        'page_size': page_size,
        'total_pages': (total + page_size - 1) // page_size,
        'array_key': array_key,
    })


def _pdf_model_data(request, cfg, page, page_size, offset, q):
    """PDF 생성 모델의 데이터를 테이블 형태로 반환"""
    from django.db.models.fields import CharField, TextField
    from django.db.models import ForeignKey, OneToOneField

    model = cfg['model']
    qs = model.objects.all().order_by('-pk')

    # 텍스트 검색
    if q:
        q_filter = Q()
        for field in model._meta.get_fields():
            if isinstance(field, (CharField, TextField)) and hasattr(field, 'column'):
                q_filter |= Q(**{f'{field.name}__icontains': q})
        if q_filter:
            qs = qs.filter(q_filter)

    total = qs.count()

    # 컬럼 자동 생성
    columns = []
    display_fields = []
    for field in model._meta.get_fields():
        if not hasattr(field, 'column'):
            if not isinstance(field, (ForeignKey, OneToOneField)):
                continue
        if field.name in ('id', 'pk'):
            continue
        if 'pdf' in field.name.lower() or 'signature' in field.name.lower():
            continue
        label = str(field.verbose_name) if hasattr(field, 'verbose_name') else field.name
        key = field.attname if isinstance(field, (ForeignKey, OneToOneField)) else field.name
        columns.append({'key': key, 'label': label})
        display_fields.append(field)
        if len(columns) >= 10:
            break

    # 데이터
    rows = []
    for obj in qs[offset:offset + page_size]:
        row = {'_pk': obj.pk, '_pdf': getattr(obj, cfg['pdf_field'], '') or ''}
        for field in display_fields:
            if isinstance(field, (ForeignKey, OneToOneField)):
                fk_obj = getattr(obj, field.name, None)
                row[field.attname] = str(fk_obj)[:40] if fk_obj else '-'
            else:
                val = getattr(obj, field.name, None)
                if val is None:
                    row[field.name] = '-'
                elif hasattr(val, 'strftime'):
                    row[field.name] = val.strftime('%Y-%m-%d %H:%M') if hasattr(val, 'hour') else val.strftime('%Y-%m-%d')
                elif isinstance(val, bool):
                    row[field.name] = val
                else:
                    s = str(val)
                    row[field.name] = s[:60] if len(s) > 60 else s
        rows.append(row)

    return JsonResponse({
        'name': cfg['label'],
        'columns': columns,
        'rows': rows,
        'total': total,
        'page': page,
        'page_size': page_size,
        'total_pages': (total + page_size - 1) // page_size,
    })


@login_required
@_admin_required
def doc_export(request, doc_id):
    """서류 데이터 Excel 다운로드"""
    import openpyxl
    from io import BytesIO
    from openpyxl.styles import Font, PatternFill

    # doc_data와 동일한 로직으로 전체 데이터 가져오기
    # page_size를 크게 설정
    request.GET = request.GET.copy()
    request.GET['page'] = '1'
    request.GET['page_size'] = '10000'

    # 내부 호출
    response = doc_data(request, doc_id)
    data = json.loads(response.content)

    if 'error' in data:
        return response

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = data.get('name', 'export')[:31]

    columns = data.get('columns', [])
    rows = data.get('rows', [])

    # 헤더
    headers = [c['label'] for c in columns]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True, size=10)
        cell.fill = PatternFill(start_color='D9E2F3', end_color='D9E2F3', fill_type='solid')

    # 데이터
    for row in rows:
        row_data = []
        for c in columns:
            val = row.get(c['key'], '')
            if isinstance(val, bool):
                val = 'Y' if val else 'N'
            row_data.append(val)
        ws.append(row_data)

    # 컬럼 너비
    for col_idx in range(1, len(columns) + 1):
        max_len = len(headers[col_idx - 1])
        for row in ws.iter_rows(min_row=2, min_col=col_idx, max_col=col_idx, max_row=min(50, ws.max_row)):
            for cell in row:
                if cell.value:
                    max_len = max(max_len, len(str(cell.value)[:30]))
        ws.column_dimensions[openpyxl.utils.get_column_letter(col_idx)].width = min(max_len + 3, 40)

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)

    name = data.get('name', 'export').replace(' ', '_')
    resp = HttpResponse(buf.read(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    resp['Content-Disposition'] = f'attachment; filename="{name}.xlsx"'
    return resp
