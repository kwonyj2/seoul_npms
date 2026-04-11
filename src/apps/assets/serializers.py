"""
assets 앱 Serializers
자재관리(materials) 구조를 기반으로 장비관리에 맞게 구현
"""
from rest_framework import serializers
from .models import (
    AssetCategory, AssetModel, Asset,
    AssetInbound, AssetOutbound, AssetReturn,
    AssetHistory, AssetRMA,
    DeviceNetworkConfig, AssetModelConfig,
    CURRENT_INSTALL_PROJECT, CURRENT_INSTALL_YEAR,
)


# ─────────────────────────────────────
# 분류 / 모델
# ─────────────────────────────────────

class AssetCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model  = AssetCategory
        fields = ['id', 'code', 'name', 'usable_years', 'order']


class AssetModelSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)

    class Meta:
        model  = AssetModel
        fields = ['id', 'manufacturer', 'model_name', 'category', 'category_name',
                  'spec', 'usable_years', 'is_active', 'note']


# ─────────────────────────────────────
# Asset (장비)
# ─────────────────────────────────────

class AssetListSerializer(serializers.ModelSerializer):
    """목록 조회용 — 핵심 정보만"""
    model_name       = serializers.CharField(source='asset_model.model_name',      read_only=True)
    manufacturer     = serializers.CharField(source='asset_model.manufacturer',    read_only=True)
    category_name    = serializers.CharField(source='asset_model.category.name',   read_only=True)
    status_display   = serializers.CharField(source='get_status_display',           read_only=True)
    school_name      = serializers.CharField(source='current_school.name',         read_only=True, default=None)
    center_name      = serializers.CharField(source='current_center.name',         read_only=True, default=None)
    replaced_from_sn = serializers.CharField(source='replaced_from.serial_number', read_only=True, default=None)

    class Meta:
        model  = Asset
        fields = [
            'id', 'serial_number', 'asset_tag',
            'model_name', 'manufacturer', 'category_name',
            'status', 'status_display',
            'school_name', 'center_name', 'install_location',
            'install_year', 'project_name',
            'installed_at', 'warranty_expire',
            'is_rma_replaced', 'replaced_from_sn',
            'created_at',
        ]


class AssetDetailSerializer(serializers.ModelSerializer):
    """상세 조회/수정용 — 전체 필드"""
    model_name       = serializers.CharField(source='asset_model.model_name',      read_only=True)
    manufacturer     = serializers.CharField(source='asset_model.manufacturer',    read_only=True)
    category_name    = serializers.CharField(source='asset_model.category.name',   read_only=True)
    status_display   = serializers.CharField(source='get_status_display',           read_only=True)
    school_name      = serializers.CharField(source='current_school.name',         read_only=True, default=None)
    center_name      = serializers.CharField(source='current_center.name',         read_only=True, default=None)
    history_count    = serializers.SerializerMethodField()
    rma_count        = serializers.SerializerMethodField()
    replaced_from_sn = serializers.CharField(source='replaced_from.serial_number', read_only=True, default=None)

    def get_history_count(self, obj):
        return obj.history.count()

    def get_rma_count(self, obj):
        return obj.rma_records.count()

    class Meta:
        model  = Asset
        fields = [
            'id', 'serial_number', 'asset_tag',
            'asset_model', 'model_name', 'manufacturer', 'category_name',
            'status', 'status_display',
            'current_center', 'center_name',
            'current_school', 'school_name',
            'install_location',
            'install_year', 'project_name',
            'purchased_at', 'installed_at', 'warranty_expire', 'disposed_at',
            'is_rma_replaced', 'replaced_from', 'replaced_from_sn',
            'note', 'created_at', 'updated_at',
            'history_count', 'rma_count',
        ]


# ─────────────────────────────────────
# AssetHistory
# ─────────────────────────────────────

class AssetHistorySerializer(serializers.ModelSerializer):
    action_display = serializers.CharField(source='get_action_display', read_only=True)
    worker_name    = serializers.SerializerMethodField()

    def get_worker_name(self, obj):
        if not obj.worker:
            return None
        return getattr(obj.worker, 'name', None) or obj.worker.username

    class Meta:
        model  = AssetHistory
        fields = [
            'id', 'action', 'action_display',
            'from_location', 'to_location',
            'worker', 'worker_name',
            'note', 'occurred_at',
        ]


# ─────────────────────────────────────
# AssetInbound (장비 입고)
# ─────────────────────────────────────

class AssetInboundSerializer(serializers.ModelSerializer):
    serial_number         = serializers.CharField(source='asset.serial_number',             read_only=True)
    asset_tag             = serializers.CharField(source='asset.asset_tag',                 read_only=True)
    model_name            = serializers.CharField(source='asset.asset_model.model_name',    read_only=True)
    manufacturer          = serializers.CharField(source='asset.asset_model.manufacturer',  read_only=True)
    category_name         = serializers.CharField(source='asset.asset_model.category.name', read_only=True)
    from_location_display = serializers.CharField(source='get_from_location_type_display',  read_only=True)
    to_location_display   = serializers.CharField(source='get_to_location_type_display',    read_only=True)
    from_center_name      = serializers.CharField(source='from_center.name', read_only=True, default=None)
    to_center_name        = serializers.CharField(source='to_center.name',   read_only=True, default=None)
    received_by_name      = serializers.SerializerMethodField()

    def get_received_by_name(self, obj):
        if not obj.received_by:
            return None
        return getattr(obj.received_by, 'name', None) or obj.received_by.username

    class Meta:
        model            = AssetInbound
        fields           = [
            'id', 'inbound_number',
            'asset', 'serial_number', 'asset_tag', 'model_name', 'manufacturer', 'category_name',
            'from_location_type', 'from_location_display',
            'from_center', 'from_center_name', 'from_location_name',
            'to_location_type', 'to_location_display',
            'to_center', 'to_center_name',
            'inbound_date',
            'received_by', 'received_by_name',
            'handover_person', 'handover_phone', 'handover_signature',
            'receiver_person', 'receiver_phone', 'receiver_signature',
            'note', 'pdf_path', 'created_at',
        ]
        read_only_fields = ['inbound_number']

    def create(self, validated_data):
        validated_data['inbound_number'] = AssetInbound.generate_number(
            validated_data.get('inbound_date')
        )
        inbound = super().create(validated_data)
        # Asset 상태 자동 변경
        asset = inbound.asset
        if inbound.to_location_type == 'warehouse':
            asset.status = 'warehouse'
            asset.current_center = None
            asset.current_school = None
        elif inbound.to_location_type == 'center' and inbound.to_center:
            asset.status = 'center'
            asset.current_center = inbound.to_center
            asset.current_school = None
        asset.save(update_fields=['status', 'current_center', 'current_school'])
        # 이력 자동 기록
        from_loc = inbound.from_location_name or inbound.get_from_location_type_display()
        to_loc = inbound.to_center.name if inbound.to_center else '창고'
        AssetHistory.objects.create(
            asset=asset, action='inbound',
            from_location=from_loc, to_location=to_loc,
            worker=inbound.received_by,
            note=f'입고번호: {inbound.inbound_number}'
        )
        return inbound


# ─────────────────────────────────────
# AssetOutbound (장비 출고)
# ─────────────────────────────────────

class AssetOutboundSerializer(serializers.ModelSerializer):
    serial_number         = serializers.CharField(source='asset.serial_number',             read_only=True)
    asset_tag             = serializers.CharField(source='asset.asset_tag',                 read_only=True)
    model_name            = serializers.CharField(source='asset.asset_model.model_name',    read_only=True)
    manufacturer          = serializers.CharField(source='asset.asset_model.manufacturer',  read_only=True)
    category_name         = serializers.CharField(source='asset.asset_model.category.name', read_only=True)
    current_status        = serializers.CharField(source='asset.get_status_display',        read_only=True)
    is_rma_replaced       = serializers.BooleanField(source='asset.is_rma_replaced',        read_only=True)
    from_location_display = serializers.CharField(source='get_from_location_type_display',  read_only=True)
    to_location_display   = serializers.CharField(source='get_to_location_type_display',    read_only=True)
    from_center_name      = serializers.CharField(source='from_center.name', read_only=True, default=None)
    to_center_name        = serializers.CharField(source='to_center.name',   read_only=True, default=None)
    to_school_name        = serializers.CharField(source='to_school.name',   read_only=True, default=None)
    issued_by_name        = serializers.SerializerMethodField()

    def get_issued_by_name(self, obj):
        if not obj.issued_by:
            return None
        return getattr(obj.issued_by, 'name', None) or obj.issued_by.username

    class Meta:
        model            = AssetOutbound
        fields           = [
            'id', 'outbound_number',
            'asset', 'serial_number', 'asset_tag', 'model_name', 'manufacturer', 'category_name',
            'current_status', 'is_rma_replaced',
            'from_location_type', 'from_location_display',
            'from_center', 'from_center_name',
            'to_location_type', 'to_location_display',
            'to_center', 'to_center_name',
            'to_school', 'to_school_name',
            'outbound_date',
            'issued_by', 'issued_by_name',
            'handover_person', 'handover_phone', 'handover_signature',
            'receiver_person', 'receiver_phone', 'receiver_signature',
            'note', 'pdf_path', 'created_at',
        ]
        read_only_fields = ['outbound_number']

    def validate(self, attrs):
        asset = attrs.get('asset') or (self.instance.asset if self.instance else None)
        if not asset:
            return attrs
        from_type = attrs.get('from_location_type',
                               self.instance.from_location_type if self.instance else 'warehouse')
        if not self.instance:
            if from_type == 'warehouse' and asset.status != 'warehouse':
                raise serializers.ValidationError(
                    f'창고 출고 불가: 장비 현재 상태가 "{asset.get_status_display()}"입니다.'
                )
            if from_type == 'center' and asset.status != 'center':
                raise serializers.ValidationError(
                    f'센터 출고 불가: 장비 현재 상태가 "{asset.get_status_display()}"입니다.'
                )
        return attrs

    def create(self, validated_data):
        validated_data['outbound_number'] = AssetOutbound.generate_number(
            validated_data.get('outbound_date')
        )
        outbound = super().create(validated_data)
        # Asset 상태 자동 변경
        asset = outbound.asset
        to_type = outbound.to_location_type
        if to_type == 'center' and outbound.to_center:
            asset.status = 'center'
            asset.current_center = outbound.to_center
            asset.current_school = None
        elif to_type == 'school' and outbound.to_school:
            asset.status = 'installed'
            asset.current_school = outbound.to_school
            if not asset.installed_at:
                asset.installed_at = outbound.outbound_date
            asset.install_year = CURRENT_INSTALL_YEAR
            asset.project_name = CURRENT_INSTALL_PROJECT
        elif to_type == 'vendor':
            asset.status = 'rma'
            asset.current_school = None
        asset.save(update_fields=['status', 'current_center', 'current_school', 'installed_at',
                                  'install_year', 'project_name'])
        # 이력 자동 기록
        from_loc = outbound.from_center.name if outbound.from_center else '창고'
        to_loc = (outbound.to_center.name if outbound.to_center else
                  outbound.to_school.name if outbound.to_school else '제조사(RMA)')
        action = 'rma_send' if to_type == 'vendor' else 'outbound'
        AssetHistory.objects.create(
            asset=asset, action=action,
            from_location=from_loc, to_location=to_loc,
            worker=outbound.issued_by,
            note=f'출고번호: {outbound.outbound_number}'
        )
        # 센터로 출고 시 → 해당 센터의 입고 이력 자동 생성
        if to_type == 'center' and outbound.to_center:
            AssetInbound.objects.create(
                inbound_number=AssetInbound.generate_number(outbound.outbound_date),
                asset=asset,
                from_location_type=outbound.from_location_type,  # warehouse or center
                from_center=outbound.from_center,                 # None이면 창고 출처
                from_location_name=from_loc,
                to_location_type='center',
                to_center=outbound.to_center,
                inbound_date=outbound.outbound_date,
                received_by=outbound.issued_by,
                handover_person=outbound.handover_person,
                handover_phone=outbound.handover_phone,
                receiver_person=outbound.receiver_person,
                receiver_phone=outbound.receiver_phone,
                note=f'출고 자동생성 (출고번호: {outbound.outbound_number})',
            )
        return outbound


# ─────────────────────────────────────
# AssetReturn (장비 반납/회수)
# ─────────────────────────────────────

class AssetReturnSerializer(serializers.ModelSerializer):
    serial_number         = serializers.CharField(source='asset.serial_number',             read_only=True)
    asset_tag             = serializers.CharField(source='asset.asset_tag',                 read_only=True)
    model_name            = serializers.CharField(source='asset.asset_model.model_name',    read_only=True)
    manufacturer          = serializers.CharField(source='asset.asset_model.manufacturer',  read_only=True)
    category_name         = serializers.CharField(source='asset.asset_model.category.name', read_only=True)
    is_rma_replaced       = serializers.BooleanField(source='asset.is_rma_replaced',        read_only=True)
    from_location_display = serializers.CharField(source='get_from_location_type_display',  read_only=True)
    to_location_display   = serializers.CharField(source='get_to_location_type_display',    read_only=True)
    from_school_name      = serializers.CharField(source='from_school.name', read_only=True, default=None)
    from_center_name      = serializers.CharField(source='from_center.name', read_only=True, default=None)
    to_center_name        = serializers.CharField(source='to_center.name',   read_only=True, default=None)
    received_by_name      = serializers.SerializerMethodField()

    def get_received_by_name(self, obj):
        if not obj.received_by:
            return None
        return getattr(obj.received_by, 'name', None) or obj.received_by.username

    class Meta:
        model            = AssetReturn
        fields           = [
            'id', 'return_number',
            'asset', 'serial_number', 'asset_tag', 'model_name', 'manufacturer', 'category_name',
            'is_rma_replaced',
            'from_location_type', 'from_location_display',
            'from_school', 'from_school_name',
            'from_center', 'from_center_name',
            'to_location_type', 'to_location_display',
            'to_center', 'to_center_name',
            'return_date', 'reason',
            'received_by', 'received_by_name',
            'handover_person', 'handover_phone', 'handover_signature',
            'receiver_person', 'receiver_phone', 'receiver_signature',
            'note', 'pdf_path', 'created_at',
        ]
        read_only_fields = ['return_number']

    def create(self, validated_data):
        validated_data['return_number'] = AssetReturn.generate_number(
            validated_data.get('return_date')
        )
        ret = super().create(validated_data)
        # Asset 상태 자동 변경
        asset = ret.asset
        if ret.to_location_type == 'center' and ret.to_center:
            asset.status = 'center'
            asset.current_center = ret.to_center
            asset.current_school = None
        elif ret.to_location_type == 'warehouse':
            asset.status = 'warehouse'
            asset.current_center = None
            asset.current_school = None
        asset.save(update_fields=['status', 'current_center', 'current_school'])
        # 이력 자동 기록
        from_loc = (ret.from_school.name if ret.from_school else
                    ret.from_center.name if ret.from_center else '출처 미상')
        to_loc = ret.to_center.name if ret.to_center else '창고'
        AssetHistory.objects.create(
            asset=asset, action='return',
            from_location=from_loc, to_location=to_loc,
            worker=ret.received_by,
            note=f'반납번호: {ret.return_number} / 사유: {ret.reason or "-"}'
        )
        return ret


# ─────────────────────────────────────
# AssetRMA
# ─────────────────────────────────────

class AssetRMASerializer(serializers.ModelSerializer):
    status_display       = serializers.CharField(source='get_status_display',             read_only=True)
    asset_serial         = serializers.CharField(source='asset.serial_number',             read_only=True)
    asset_model_name     = serializers.CharField(source='asset.asset_model.model_name',   read_only=True)
    handled_by_name      = serializers.SerializerMethodField()
    replacement_asset_sn = serializers.CharField(
        source='replacement_asset.serial_number', read_only=True, default=None
    )

    def get_handled_by_name(self, obj):
        if not obj.handled_by:
            return None
        return getattr(obj.handled_by, 'name', None) or obj.handled_by.username

    class Meta:
        model  = AssetRMA
        fields = [
            'id', 'asset', 'asset_serial', 'asset_model_name',
            'rma_number', 'status', 'status_display',
            'reason', 'sent_date', 'returned_date',
            'handled_by', 'handled_by_name',
            'new_serial', 'replacement_asset', 'replacement_asset_sn',
            'note', 'created_at',
        ]


# ─────────────────────────────────────
# DeviceNetworkConfig (장비별 개별 설정)
# ─────────────────────────────────────

class DeviceNetworkConfigSerializer(serializers.ModelSerializer):
    asset_serial = serializers.CharField(source='asset.serial_number',          read_only=True)
    asset_model  = serializers.CharField(source='asset.asset_model.model_name', read_only=True)

    class Meta:
        model  = DeviceNetworkConfig
        fields = [
            'id', 'asset', 'asset_serial', 'asset_model',
            'mgmt_ip', 'mgmt_subnet', 'mgmt_gateway',
            'vlan_mgmt', 'vlan_data',
            'uplink_port', 'uplink_speed',
            'ssh_enabled', 'snmp_community',
            'firmware_ver', 'last_config_backup',
            'config_note', 'updated_at',
        ]
        read_only_fields = ['updated_at']


# ─────────────────────────────────────
# AssetModelConfig (모델별 표준 설정)
# ─────────────────────────────────────

class AssetModelConfigSerializer(serializers.ModelSerializer):
    model_name      = serializers.CharField(source='asset_model.model_name',    read_only=True)
    manufacturer    = serializers.CharField(source='asset_model.manufacturer',  read_only=True)
    category_name   = serializers.CharField(source='asset_model.category.name', read_only=True)
    updated_by_name = serializers.SerializerMethodField()

    def get_updated_by_name(self, obj):
        if not obj.updated_by:
            return None
        return getattr(obj.updated_by, 'name', None) or obj.updated_by.username

    class Meta:
        model  = AssetModelConfig
        fields = [
            'id', 'asset_model', 'model_name', 'manufacturer', 'category_name',
            'vlan_mgmt', 'vlan_data',
            'uplink_port', 'uplink_speed',
            'ssh_enabled', 'snmp_community',
            'firmware_ver', 'config_commands',
            'config_note', 'updated_at', 'updated_by', 'updated_by_name',
        ]
        read_only_fields = ['updated_at']
