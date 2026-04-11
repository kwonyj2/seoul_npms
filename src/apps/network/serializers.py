from rest_framework import serializers
from .models import (
    NetworkDevice, NetworkPort, NetworkLink,
    NetworkTopology, NetworkEvent, SnmpDevice, SnmpMetric, NetworkCommand
)


class NetworkPortSerializer(serializers.ModelSerializer):
    class Meta:
        model = NetworkPort
        fields = ['id', 'port_num', 'port_name', 'status', 'speed_mbps',
                  'vlan_id', 'connected_mac', 'is_poe', 'poe_power_mw', 'updated_at']
        read_only_fields = ['id', 'updated_at']


class SnmpDeviceSerializer(serializers.ModelSerializer):
    class Meta:
        model = SnmpDevice
        fields = ['community', 'version', 'port', 'poll_interval_s',
                  'is_active', 'last_poll_at']


class NetworkDeviceListSerializer(serializers.ModelSerializer):
    school_name    = serializers.CharField(source='school.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    type_display   = serializers.CharField(source='get_device_type_display', read_only=True)
    asset_id       = serializers.PrimaryKeyRelatedField(source='asset', read_only=True)

    class Meta:
        model = NetworkDevice
        fields = ['id', 'school', 'school_name', 'device_type', 'type_display',
                  'name', 'ip_address', 'serial_number', 'status', 'status_display',
                  'asset_id', 'last_seen', 'snmp_enabled', 'ssh_enabled', 'created_at']


class NetworkDeviceDetailSerializer(serializers.ModelSerializer):
    school_name   = serializers.CharField(source='school.name', read_only=True)
    ports         = NetworkPortSerializer(many=True, read_only=True)
    snmp          = SnmpDeviceSerializer(read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = NetworkDevice
        fields = ['id', 'school', 'school_name', 'device_type', 'name',
                  'ip_address', 'mac_address', 'hostname', 'manufacturer',
                  'model', 'firmware', 'serial_number', 'status', 'status_display',
                  'location', 'snmp_enabled', 'ssh_enabled', 'last_seen',
                  'uptime_seconds', 'ports', 'snmp', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class NetworkTopologySerializer(serializers.ModelSerializer):
    school_name = serializers.CharField(source='school.name', read_only=True)

    class Meta:
        model = NetworkTopology
        fields = ['id', 'school', 'school_name', 'topology_data', 'scanned_at']
        read_only_fields = ['id', 'scanned_at']


class NetworkEventSerializer(serializers.ModelSerializer):
    device_name    = serializers.CharField(source='device.name', read_only=True)
    device_ip      = serializers.CharField(source='device.ip_address', read_only=True)
    school_name    = serializers.CharField(source='device.school.name', read_only=True)
    severity_display = serializers.CharField(source='get_severity_display', read_only=True)
    event_display  = serializers.CharField(source='get_event_type_display', read_only=True)

    class Meta:
        model = NetworkEvent
        fields = ['id', 'device', 'device_name', 'device_ip', 'school_name',
                  'event_type', 'event_display', 'severity', 'severity_display',
                  'message', 'is_resolved', 'resolved_at', 'incident',
                  'occurred_at']
        read_only_fields = ['id', 'occurred_at']


class SnmpMetricSerializer(serializers.ModelSerializer):
    class Meta:
        model = SnmpMetric
        fields = ['id', 'device', 'metric_name', 'oid', 'value', 'collected_at']
        read_only_fields = ['id', 'collected_at']


class NetworkCommandSerializer(serializers.ModelSerializer):
    executed_by_name = serializers.CharField(source='executed_by.name', read_only=True)
    device_name      = serializers.CharField(source='device.name', read_only=True)

    class Meta:
        model = NetworkCommand
        fields = ['id', 'device', 'device_name', 'command_type', 'command',
                  'result', 'status', 'executed_by', 'executed_by_name', 'executed_at']
        read_only_fields = ['id', 'result', 'status', 'executed_by', 'executed_at']
