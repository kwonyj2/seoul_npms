from rest_framework import serializers
from .models import SupportCenter, SchoolType, School, SchoolBuilding, SchoolFloor, SchoolRoom, SchoolContact, SchoolNetwork


class SupportCenterSerializer(serializers.ModelSerializer):
    school_count = serializers.SerializerMethodField()

    class Meta:
        model = SupportCenter
        fields = ['id', 'code', 'name', 'address', 'phone', 'lat', 'lng', 'url', 'is_active', 'school_count']

    def get_school_count(self, obj):
        return obj.schools.filter(is_active=True).count()


class SchoolTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = SchoolType
        fields = ['id', 'code', 'name', 'order']


class SchoolContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = SchoolContact
        fields = ['id', 'name', 'phone', 'position', 'email', 'is_primary']


class SchoolBuildingSerializer(serializers.ModelSerializer):
    class Meta:
        model = SchoolBuilding
        fields = ['id', 'name', 'code', 'floors', 'basement', 'note', 'order']


class SchoolFloorSerializer(serializers.ModelSerializer):
    class Meta:
        model = SchoolFloor
        fields = ['id', 'floor_num', 'floor_name']


class SchoolRoomSerializer(serializers.ModelSerializer):
    class Meta:
        model = SchoolRoom
        fields = ['id', 'name', 'room_type', 'note']


class SchoolNetworkSerializer(serializers.ModelSerializer):
    class Meta:
        model = SchoolNetwork
        fields = '__all__'


class SchoolListSerializer(serializers.ModelSerializer):
    support_center_name = serializers.CharField(source='support_center.name', read_only=True)
    school_type_name    = serializers.CharField(source='school_type.name', read_only=True)
    active_incidents    = serializers.SerializerMethodField()
    device_count        = serializers.SerializerMethodField()
    network_docs        = serializers.SerializerMethodField()

    class Meta:
        model = School
        fields = ['id', 'name', 'support_center', 'support_center_name',
                  'school_type', 'school_type_name', 'address', 'lat', 'lng',
                  'phone', 'is_active', 'active_incidents', 'device_count', 'network_docs']

    def get_active_incidents(self, obj):
        if hasattr(obj, '_active_incidents'):
            return obj._active_incidents
        return obj.incidents.exclude(status='completed').count()

    def get_device_count(self, obj):
        from apps.schools.models import SchoolEquipment
        cats = obj.equipment_list.values_list('category', flat=True)
        switch = sum(1 for c in cats if '스위치' in c and 'PoE' not in c)
        poe    = sum(1 for c in cats if 'PoE' in c)
        ap     = sum(1 for c in cats if 'AP' in c or '무선' in c)
        return {'switch': switch, 'poe': poe, 'ap': ap,
                'total': obj.equipment_list.count()}

    def get_network_docs(self, obj):
        """5개 문서 카테고리별 첫 번째 파일 URL + 총 건수 반환
        산출물/테크센터/ 하위 폴더에서 keyword로 폴더를 찾고 학교명으로 파일 매칭
        """
        import os
        from urllib.parse import quote
        from django.conf import settings
        from apps.schools.views import NETDOC_CATEGORIES, _find_nas_doc_folders

        result = {}
        nas_root = getattr(settings, 'NAS_MEDIA_ROOT', settings.MEDIA_ROOT)
        media_url = settings.MEDIA_URL

        INLINE_KEYS = {'건물정보', '전산실랙'}

        for cat in NETDOC_CATEGORIES:
            matches = []
            for folder_abs in _find_nas_doc_folders(nas_root, cat['keyword']):
                rel_path = os.path.relpath(folder_abs, nas_root)
                url_base = f"{media_url}{quote(rel_path, safe='/')}/"
                for fname in sorted(os.listdir(folder_abs)):
                    if os.path.isdir(os.path.join(folder_abs, fname)):
                        continue
                    ext = os.path.splitext(fname)[1].lower()
                    if ext not in cat['exts']:
                        continue
                    if obj.name in fname:
                        matches.append({'name': fname, 'url': url_base + quote(fname)})

            if matches:
                result[cat['key']] = {
                    'url': matches[0]['url'],
                    'count': len(matches),
                    'inline': cat['key'] in INLINE_KEYS,
                }
            else:
                result[cat['key']] = None

        return result


class SchoolDetailSerializer(serializers.ModelSerializer):
    support_center = SupportCenterSerializer(read_only=True)
    school_type    = SchoolTypeSerializer(read_only=True)
    buildings      = SchoolBuildingSerializer(many=True, read_only=True)
    contacts       = SchoolContactSerializer(many=True, read_only=True)

    class Meta:
        model = School
        fields = '__all__'


class SchoolGISSerializer(serializers.ModelSerializer):
    """카카오맵 마커 용 경량 시리얼라이저"""
    support_center_name = serializers.CharField(source='support_center.name', read_only=True)
    school_type_name    = serializers.CharField(source='school_type.name', read_only=True)
    active_incidents    = serializers.SerializerMethodField()

    class Meta:
        model = School
        fields = ['id', 'name', 'lat', 'lng', 'support_center_name', 'school_type_name',
                  'address', 'phone', 'active_incidents']

    def get_active_incidents(self, obj):
        if hasattr(obj, '_active_incidents'):
            return obj._active_incidents
        return obj.incidents.exclude(status='completed').count()
