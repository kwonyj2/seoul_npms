"""
범용 DB 관리 API — Django Admin 대체
superadmin 전용, 모델 메타데이터 기반 자동 CRUD
"""
import json
from django.apps import apps
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.db.models import Q, ForeignKey, OneToOneField, ManyToManyField
from django.db.models.fields import (
    CharField, TextField, IntegerField, FloatField, DecimalField,
    BooleanField, DateField, DateTimeField, AutoField, BigAutoField,
)
from django.db.models.fields.files import FileField, ImageField

# superadmin 전용
def _superadmin_required(view_func):
    from functools import wraps
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'error': '로그인 필요'}, status=401)
        if request.user.role != 'superadmin':
            return JsonResponse({'error': 'superadmin 전용'}, status=403)
        return view_func(request, *args, **kwargs)
    return _wrapped


# 노출할 앱 (시스템 내부 앱 제외)
ALLOWED_APPS = [
    'accounts', 'incidents', 'schools', 'workforce', 'assets', 'materials',
    'gps', 'progress', 'reports', 'audit', 'nas', 'photos', 'education',
    'bulletin', 'statistics', 'network', 'wbs', 'sysconfig',
    'django_celery_beat', 'django_celery_results',
]

# 편집 불가 필드
READONLY_FIELDS = {'id', 'pk', 'created_at', 'updated_at', 'date_joined'}


def _get_field_info(field):
    """모델 필드 → 프론트 렌더링용 메타 정보"""
    info = {
        'name': field.name,
        'label': str(field.verbose_name) if hasattr(field, 'verbose_name') else field.name,
        'required': not field.blank and not field.has_default() and field.name != 'id',
        'readonly': field.name in READONLY_FIELDS or isinstance(field, (AutoField, BigAutoField)),
        'type': 'text',
    }
    if isinstance(field, (AutoField, BigAutoField)):
        info['type'] = 'auto'
    elif isinstance(field, BooleanField):
        info['type'] = 'boolean'
    elif isinstance(field, (DateTimeField,)):
        info['type'] = 'datetime'
    elif isinstance(field, (DateField,)):
        info['type'] = 'date'
    elif isinstance(field, (IntegerField,)):
        info['type'] = 'integer'
    elif isinstance(field, (FloatField, DecimalField)):
        info['type'] = 'number'
    elif isinstance(field, (TextField,)):
        info['type'] = 'textarea'
    elif isinstance(field, (ImageField, FileField)):
        info['type'] = 'file'
        info['readonly'] = True  # 파일은 목록에서만 표시
    elif isinstance(field, (ForeignKey, OneToOneField)):
        info['type'] = 'fk'
        related = field.related_model
        info['fk_app'] = related._meta.app_label
        info['fk_model'] = related._meta.model_name
        info['name'] = field.attname  # _id 필드명
        info['label'] = str(field.verbose_name)
        # 선택지 로드 (1000개 이하만)
        try:
            count = related.objects.count()
            if count <= 1000:
                choices = []
                for obj in related.objects.all()[:1000]:
                    choices.append({'id': obj.pk, 'label': str(obj)[:60]})
                info['choices'] = choices
            else:
                info['choices_count'] = count
        except Exception:
            pass
    elif isinstance(field, CharField) and field.choices:
        info['type'] = 'select'
        info['choices'] = [{'id': k, 'label': str(v)} for k, v in field.choices]

    if isinstance(field, CharField) and field.max_length:
        info['max_length'] = field.max_length

    return info


def _serialize_value(obj, field):
    """모델 인스턴스의 필드 값을 JSON 직렬화"""
    val = getattr(obj, field.name, None)
    if val is None:
        return None
    if isinstance(field, (DateTimeField,)):
        return val.strftime('%Y-%m-%d %H:%M:%S')
    if isinstance(field, (DateField,)):
        return val.strftime('%Y-%m-%d')
    if isinstance(field, (ForeignKey, OneToOneField)):
        fk_id = getattr(obj, field.attname, None)
        fk_obj = getattr(obj, field.name, None)
        return {'id': fk_id, 'label': str(fk_obj)[:60] if fk_obj else '-'}
    if isinstance(field, (ImageField, FileField)):
        return str(val) if val else None
    if isinstance(field, (DecimalField,)):
        return float(val) if val is not None else None
    return val


@login_required
@_superadmin_required
def db_schema(request):
    """전체 앱/모델 트리 + 필드 스키마"""
    tree = {}
    for app_label in ALLOWED_APPS:
        try:
            app_config = apps.get_app_config(app_label)
        except LookupError:
            continue
        models_info = []
        for model in app_config.get_models():
            count = model.objects.count()
            models_info.append({
                'name': model._meta.model_name,
                'label': str(model._meta.verbose_name),
                'count': count,
            })
        if models_info:
            tree[app_label] = {
                'label': app_config.verbose_name or app_label,
                'models': sorted(models_info, key=lambda m: m['label']),
            }
    return JsonResponse({'tree': tree})


@login_required
@_superadmin_required
def db_model_schema(request, app_label, model_name):
    """특정 모델의 필드 스키마"""
    try:
        model = apps.get_model(app_label, model_name)
    except LookupError:
        return JsonResponse({'error': '모델을 찾을 수 없습니다.'}, status=404)

    fields = []
    for field in model._meta.get_fields():
        if isinstance(field, ManyToManyField):
            continue
        if not hasattr(field, 'column') and not isinstance(field, (ForeignKey, OneToOneField)):
            continue  # reverse relations 제외
        try:
            fields.append(_get_field_info(field))
        except Exception:
            pass

    return JsonResponse({
        'app': app_label,
        'model': model_name,
        'label': str(model._meta.verbose_name),
        'fields': fields,
        'count': model.objects.count(),
    })


@login_required
@_superadmin_required
def db_crud(request, app_label, model_name, pk=None):
    """범용 CRUD 엔드포인트"""
    try:
        model = apps.get_model(app_label, model_name)
    except LookupError:
        return JsonResponse({'error': '모델을 찾을 수 없습니다.'}, status=404)

    if app_label not in ALLOWED_APPS:
        return JsonResponse({'error': '접근 불가 앱'}, status=403)

    # ── GET: 목록 또는 상세 ──────────────────────────
    if request.method == 'GET':
        if pk:
            try:
                obj = model.objects.get(pk=pk)
            except model.DoesNotExist:
                return JsonResponse({'error': '레코드 없음'}, status=404)
            row = {}
            for field in model._meta.get_fields():
                if isinstance(field, ManyToManyField) or not hasattr(field, 'column'):
                    if not isinstance(field, (ForeignKey, OneToOneField)):
                        continue
                try:
                    row[field.attname if isinstance(field, (ForeignKey, OneToOneField)) else field.name] = _serialize_value(obj, field)
                except Exception:
                    pass
            return JsonResponse({'row': row})

        # 목록
        page = max(1, int(request.GET.get('page', 1)))
        page_size = min(100, int(request.GET.get('page_size', 50)))
        q = request.GET.get('q', '').strip()
        sort = request.GET.get('sort', '-pk')
        offset = (page - 1) * page_size

        qs = model.objects.all()

        # 텍스트 검색 (CharField, TextField만)
        if q:
            q_filter = Q()
            for field in model._meta.get_fields():
                if isinstance(field, (CharField, TextField)) and hasattr(field, 'column'):
                    q_filter |= Q(**{f'{field.name}__icontains': q})
            if q_filter:
                qs = qs.filter(q_filter)

        # 정렬
        try:
            qs = qs.order_by(sort)
        except Exception:
            qs = qs.order_by('-pk')

        total = qs.count()

        # 목록용 필드 (처음 8개만)
        display_fields = []
        for field in model._meta.get_fields():
            if isinstance(field, ManyToManyField):
                continue
            if not hasattr(field, 'column') and not isinstance(field, (ForeignKey, OneToOneField)):
                continue
            display_fields.append(field)
            if len(display_fields) >= 8:
                break

        rows = []
        for obj in qs[offset:offset + page_size]:
            row = {'pk': obj.pk}
            for field in display_fields:
                key = field.attname if isinstance(field, (ForeignKey, OneToOneField)) else field.name
                row[key] = _serialize_value(obj, field)
            rows.append(row)

        return JsonResponse({
            'rows': rows,
            'total': total,
            'page': page,
            'page_size': page_size,
            'total_pages': (total + page_size - 1) // page_size,
        })

    # ── POST: 신규 생성 ─────────────────────────────
    if request.method == 'POST':
        try:
            body = json.loads(request.body)
        except Exception:
            return JsonResponse({'error': '잘못된 요청'}, status=400)
        try:
            obj = model(**_clean_data(model, body))
            obj.full_clean()
            obj.save()
            return JsonResponse({'ok': True, 'pk': obj.pk})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)

    # ── PATCH: 수정 ──────────────────────────────────
    if request.method == 'PATCH' and pk:
        try:
            body = json.loads(request.body)
        except Exception:
            return JsonResponse({'error': '잘못된 요청'}, status=400)
        try:
            obj = model.objects.get(pk=pk)
            cleaned = _clean_data(model, body)
            for k, v in cleaned.items():
                setattr(obj, k, v)
            obj.full_clean()
            obj.save()
            return JsonResponse({'ok': True, 'pk': obj.pk})
        except model.DoesNotExist:
            return JsonResponse({'error': '레코드 없음'}, status=404)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)

    # ── DELETE: 삭제 ─────────────────────────────────
    if request.method == 'DELETE' and pk:
        try:
            obj = model.objects.get(pk=pk)
            obj.delete()
            return JsonResponse({'ok': True})
        except model.DoesNotExist:
            return JsonResponse({'error': '레코드 없음'}, status=404)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)

    return JsonResponse({'error': '허용되지 않는 메서드'}, status=405)


def _clean_data(model, body):
    """프론트 JSON → 모델 필드에 맞게 정제"""
    cleaned = {}
    field_map = {}
    for field in model._meta.get_fields():
        if hasattr(field, 'column'):
            field_map[field.name] = field
            if isinstance(field, (ForeignKey, OneToOneField)):
                field_map[field.attname] = field

    for key, val in body.items():
        if key in READONLY_FIELDS or key in ('pk', 'id'):
            continue
        field = field_map.get(key)
        if not field:
            continue

        # 빈 문자열 → None (nullable 필드)
        if val == '' and field.null:
            val = None

        # FK: dict에서 id 추출
        if isinstance(field, (ForeignKey, OneToOneField)):
            if isinstance(val, dict):
                val = val.get('id')
            cleaned[field.attname] = val if val else None
        elif isinstance(field, BooleanField):
            cleaned[field.name] = bool(val)
        elif isinstance(field, (IntegerField,)) and val is not None and val != '':
            cleaned[field.name] = int(val)
        elif isinstance(field, (FloatField, DecimalField)) and val is not None and val != '':
            cleaned[field.name] = float(val)
        else:
            cleaned[field.name] = val

    return cleaned
