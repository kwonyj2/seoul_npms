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
        """5개 문서 카테고리별 첫 번째 파일 URL + 총 건수 반환"""
        import os, glob
        from urllib.parse import quote
        from django.conf import settings

        CATS = [
            {'key': '구성도',  'folder': '구성도',   'prefix': '구성도_',  'exts': ['.pptx', '.ppt'],        'inline': False},
            {'key': '선번장',  'folder': '선번장',   'prefix': '선번장_',  'exts': ['.xlsx', '.xlsm'],       'inline': False},
            {'key': '랙실장도','folder': '랙실장도', 'prefix': '랙실장도_','exts': ['.xlsx', '.xlsm'],       'inline': False},
            {'key': '건물정보','folder': '건물 정보','prefix': '건물정보_','exts': ['.pdf'],                  'inline': True},
            {'key': '전산실랙','folder': '전산실랙', 'prefix': '전산실랙_','exts': ['.jpg', '.jpeg', '.png'],'inline': True},
        ]
        result = {}
        media_root = settings.MEDIA_ROOT
        media_url  = settings.MEDIA_URL

        for cat in CATS:
            folder_abs = os.path.join(media_root, 'data', cat['folder'])
            matches = []
            # 학교명 기반 레거시 파일 (prefix_학교명*.ext, prefix_학교명_번호.ext 포함)
            if os.path.isdir(folder_abs):
                for ext in cat['exts']:
                    pattern = os.path.join(folder_abs, f"{cat['prefix']}{obj.name}*{ext}")
                    found = [f for f in glob.glob(pattern) if os.path.isfile(f)]
                    matches.extend(sorted(found))
            # pk 서브폴더
            pk_dir = os.path.join(folder_abs, str(obj.pk))
            if os.path.isdir(pk_dir):
                for ext in cat['exts']:
                    pattern = os.path.join(pk_dir, f"*{ext}")
                    found = [f for f in glob.glob(pattern) if os.path.isfile(f)]
                    matches.extend(sorted(found))

            if matches:
                first = matches[0]
                # 파일이 pk_dir 안에 있는지 확인해 URL 구성
                if first.startswith(pk_dir + os.sep):
                    fname = os.path.basename(first)
                    url = f"{media_url}data/{quote(cat['folder'])}/{obj.pk}/{quote(fname)}"
                else:
                    fname = os.path.basename(first)
                    url = f"{media_url}data/{quote(cat['folder'])}/{quote(fname)}"
                result[cat['key']] = {'url': url, 'count': len(matches), 'inline': cat['inline']}
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
