"""
assets 신호 처리
DeviceNetworkConfig 저장 시 → NetworkDevice 자동 생성/동기화
Asset 설치/이동 시 → NetworkDevice school 자동 갱신
"""
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Asset, DeviceNetworkConfig

# AssetCategory.code → NetworkDevice.device_type 매핑
_CAT_TO_TYPE = {
    'switch':     'switch',
    'poe_switch': 'poe_switch',
    'ap':         'ap',
    'router':     'router',
    'server':     'server',
    'other':      'switch',
}


def _sync_network_device(config: DeviceNetworkConfig):
    """DeviceNetworkConfig → NetworkDevice 동기화 (내부 함수)"""
    from apps.network.models import NetworkDevice, SnmpDevice

    asset = config.asset

    # IP 없거나 학교 미설치면 NMS 등록 불필요
    if not config.mgmt_ip or not asset.current_school:
        return

    cat_code = ''
    if asset.asset_model and asset.asset_model.category:
        cat_code = asset.asset_model.category.code
    device_type = _CAT_TO_TYPE.get(cat_code, 'switch')

    mfr   = asset.asset_model.manufacturer if asset.asset_model else ''
    model = asset.asset_model.model_name   if asset.asset_model else ''
    name  = f'{model} ({asset.serial_number})' if model else asset.serial_number

    nd, _ = NetworkDevice.objects.update_or_create(
        asset=asset,
        defaults={
            'school':        asset.current_school,
            'device_type':   device_type,
            'name':          name,
            'ip_address':    config.mgmt_ip,
            'manufacturer':  mfr,
            'model':         model,
            'serial_number': asset.serial_number,
            'location':      asset.install_location,
            'snmp_enabled':  bool(config.snmp_community),
            'ssh_enabled':   config.ssh_enabled,
            'firmware':      config.firmware_ver,
        }
    )

    # SNMP 설정 동기화
    if config.snmp_community:
        SnmpDevice.objects.update_or_create(
            device=nd,
            defaults={
                'community': config.snmp_community,
                'version':   'v2c',
                'is_active': True,
            }
        )
    else:
        # SNMP 비활성화
        SnmpDevice.objects.filter(device=nd).update(is_active=False)


@receiver(post_save, sender=DeviceNetworkConfig)
def on_network_config_saved(sender, instance, **kwargs):
    """네트워크 설정 저장 시 NetworkDevice 자동 생성/갱신"""
    _sync_network_device(instance)


@receiver(post_save, sender=Asset)
def on_asset_saved(sender, instance, **kwargs):
    """Asset 학교/위치 변경 시 NetworkDevice 갱신"""
    try:
        config = instance.network_config  # DeviceNetworkConfig (OneToOne)
    except DeviceNetworkConfig.DoesNotExist:
        return

    if instance.current_school and config.mgmt_ip:
        from apps.network.models import NetworkDevice
        NetworkDevice.objects.filter(asset=instance).update(
            school=instance.current_school,
            location=instance.install_location,
            serial_number=instance.serial_number,
        )
    elif not instance.current_school:
        # 학교 미설치(창고/폐기 등) → NMS에서 비활성 처리
        from apps.network.models import NetworkDevice
        NetworkDevice.objects.filter(asset=instance).update(
            status='unknown',
        )
