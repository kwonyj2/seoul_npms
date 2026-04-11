from django.contrib import admin
from .models import (
    AssetCategory, AssetModel, Asset, AssetHistory,
    AssetInbound, AssetOutbound, AssetReturn, AssetRMA,
    DeviceNetworkConfig, AssetModelConfig,
)


@admin.register(AssetCategory)
class AssetCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'order')
    ordering     = ('order', 'name')


@admin.register(AssetModel)
class AssetModelAdmin(admin.ModelAdmin):
    list_display  = ('manufacturer', 'model_name', 'category', 'usable_years', 'is_active')
    list_filter   = ('category', 'is_active')
    search_fields = ('model_name', 'manufacturer')


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display  = ('serial_number', 'asset_tag', 'asset_model', 'status',
                     'is_rma_replaced', 'current_school', 'current_center')
    list_filter   = ('status', 'asset_model__category', 'is_rma_replaced')
    search_fields = ('serial_number', 'asset_tag')
    raw_id_fields = ('asset_model', 'current_center', 'current_school', 'replaced_from')


@admin.register(AssetHistory)
class AssetHistoryAdmin(admin.ModelAdmin):
    list_display  = ('asset', 'action', 'occurred_at', 'worker')
    list_filter   = ('action',)
    search_fields = ('asset__serial_number',)
    raw_id_fields = ('asset', 'worker')


@admin.register(AssetInbound)
class AssetInboundAdmin(admin.ModelAdmin):
    list_display  = ('inbound_number', 'asset', 'inbound_date',
                     'from_location_type', 'to_location_type')
    list_filter   = ('from_location_type', 'to_location_type')
    search_fields = ('inbound_number', 'asset__serial_number')
    raw_id_fields = ('asset', 'from_center', 'to_center', 'received_by')


@admin.register(AssetOutbound)
class AssetOutboundAdmin(admin.ModelAdmin):
    list_display  = ('outbound_number', 'asset', 'outbound_date',
                     'from_location_type', 'to_location_type')
    list_filter   = ('from_location_type', 'to_location_type')
    search_fields = ('outbound_number', 'asset__serial_number')
    raw_id_fields = ('asset', 'from_center', 'to_center', 'to_school', 'issued_by')


@admin.register(AssetReturn)
class AssetReturnAdmin(admin.ModelAdmin):
    list_display  = ('return_number', 'asset', 'return_date',
                     'from_location_type', 'to_location_type', 'to_center')
    list_filter   = ('from_location_type', 'to_location_type')
    search_fields = ('return_number', 'asset__serial_number')
    raw_id_fields = ('asset', 'from_school', 'from_center', 'to_center', 'received_by')


@admin.register(AssetRMA)
class AssetRMAAdmin(admin.ModelAdmin):
    list_display  = ('rma_number', 'asset', 'status', 'sent_date', 'returned_date')
    list_filter   = ('status',)
    search_fields = ('rma_number', 'asset__serial_number')
    raw_id_fields = ('asset', 'replacement_asset', 'handled_by')


@admin.register(DeviceNetworkConfig)
class DeviceNetworkConfigAdmin(admin.ModelAdmin):
    list_display  = ('asset', 'mgmt_ip', 'vlan_mgmt', 'ssh_enabled')
    search_fields = ('asset__serial_number', 'mgmt_ip')
    raw_id_fields = ('asset',)


@admin.register(AssetModelConfig)
class AssetModelConfigAdmin(admin.ModelAdmin):
    list_display  = ('asset_model', 'vlan_mgmt', 'firmware_ver', 'ssh_enabled')
    search_fields = ('asset_model__model_name', 'asset_model__manufacturer')
    raw_id_fields = ('asset_model', 'updated_by')
