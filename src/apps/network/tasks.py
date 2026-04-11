from config.celery import app as celery_app
import logging
import os
import json

logger = logging.getLogger(__name__)

# 일괄 분석 진행 상태 캐시 키
BULK_DIAGRAM_KEY = 'bulk_diagram_progress'


@celery_app.task(bind=True, max_retries=3)
def execute_network_command(self, command_id):
    """원격 명령 비동기 실행"""
    from .models import NetworkCommand
    from django.utils import timezone
    try:
        cmd = NetworkCommand.objects.select_related('device').get(id=command_id)
        cmd.status = 'running'
        cmd.save(update_fields=['status'])

        device = cmd.device
        result = ''

        if device.ssh_enabled and device.ip_address:
            try:
                import paramiko
                client = paramiko.SSHClient()
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                client.connect(device.ip_address, timeout=10, username='admin', password='')
                stdin, stdout, stderr = client.exec_command(cmd.command, timeout=30)
                result = stdout.read().decode() + stderr.read().decode()
                client.close()
                cmd.status = 'success'
            except Exception as e:
                result = str(e)
                cmd.status = 'failed'
        else:
            result = 'SSH가 비활성화된 장비입니다.'
            cmd.status = 'failed'

        cmd.result = result
        cmd.save(update_fields=['result', 'status'])
    except NetworkCommand.DoesNotExist:
        logger.error(f'NetworkCommand {command_id} not found')
    except Exception as exc:
        logger.error(f'Command execution error: {exc}')
        raise self.retry(exc=exc, countdown=30)


@celery_app.task
def poll_snmp_devices():
    """SNMP 장비 주기적 폴링"""
    from .models import SnmpDevice, SnmpMetric, NetworkDevice
    from django.utils import timezone

    try:
        from pysnmp.hlapi import (
            getCmd, SnmpEngine, CommunityData, UdpTransportTarget,
            ContextData, ObjectType, ObjectIdentity
        )
    except ImportError:
        logger.warning('pysnmp not installed, skipping SNMP polling')
        return

    active_devices = SnmpDevice.objects.filter(is_active=True).select_related('device')
    polled = 0
    for snmp_dev in active_devices:
        device = snmp_dev.device
        if not device.ip_address:
            continue
        try:
            for error_indication, error_status, error_index, var_binds in getCmd(
                SnmpEngine(),
                CommunityData(snmp_dev.community),
                UdpTransportTarget((device.ip_address, snmp_dev.port), timeout=3, retries=1),
                ContextData(),
                ObjectType(ObjectIdentity('1.3.6.1.2.1.1.1.0')),
                ObjectType(ObjectIdentity('1.3.6.1.2.1.1.3.0')),
            ):
                if not error_indication and not error_status:
                    now = timezone.now()
                    metrics = []
                    for varBind in var_binds:
                        metrics.append(SnmpMetric(
                            device=device,
                            metric_name=str(varBind[0]),
                            oid=str(varBind[0]),
                            value=str(varBind[1]),
                            collected_at=now,
                        ))
                    if metrics:
                        SnmpMetric.objects.bulk_create(metrics)
                    device.status = 'up'
                    device.last_seen = now
                    device.save(update_fields=['status', 'last_seen'])
                else:
                    device.status = 'down'
                    device.save(update_fields=['status'])
                polled += 1
                snmp_dev.last_poll_at = timezone.now()
                snmp_dev.save(update_fields=['last_poll_at'])
                break
        except Exception as e:
            logger.warning(f'SNMP poll error {device.ip_address}: {e}')
            device.status = 'unknown'
            device.save(update_fields=['status'])
    logger.info(f'SNMP polling complete: {polled} devices')


# ── 구성도 이미지 일괄 분석 ─────────────────────────────────────

DIAGRAM_PROMPT = """이 네트워크 구성도 이미지를 분석해서 정확히 아래 JSON 형식만 출력해줘. 설명 없이 JSON만.

{
  "nodes": [
    {"name": "장비명", "device_type": "switch|poe_switch|ap|router|firewall|server", "model": "모델명(없으면 빈문자열)", "location": "설치위치(없으면 빈문자열)", "network_type": "교사망|학생망|무선망|전화망|기타망|빈문자열"}
  ],
  "edges": [
    {"from": "출발장비명", "to": "도착장비명", "cable_type": "광|Cat6|Cat5e|Cat5|미확인", "network_type": "교사망|학생망|무선망|전화망|기타망|빈문자열"}
  ]
}

device_type 분류 기준:
- firewall: 방화벽, UTM
- router: 라우터, L3스위치
- switch: 일반 스위치, L2스위치
- poe_switch: PoE 스위치
- ap: 무선AP, WiFi
- server: 서버, NAS"""


def _analyze_image_with_claude(image_path: str) -> dict:
    """Claude Vision API로 구성도 이미지 분석 → topology dict 반환"""
    import anthropic
    import base64

    api_key = os.environ.get('ANTHROPIC_API_KEY', '')
    if not api_key:
        raise ValueError('ANTHROPIC_API_KEY가 설정되지 않았습니다.')

    with open(image_path, 'rb') as f:
        image_data = base64.standard_b64encode(f.read()).decode('utf-8')

    ext = os.path.splitext(image_path)[1].lower()
    media_type = {'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'png': 'image/png'}.get(ext.lstrip('.'), 'image/jpeg')

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model='claude-sonnet-4-6',
        max_tokens=4096,
        messages=[{
            'role': 'user',
            'content': [
                {'type': 'image', 'source': {'type': 'base64', 'media_type': media_type, 'data': image_data}},
                {'type': 'text', 'text': DIAGRAM_PROMPT},
            ],
        }],
    )
    text = message.content[0].text.strip()
    # ```json ... ``` 블록 제거
    if text.startswith('```'):
        text = text.split('```')[1]
        if text.startswith('json'):
            text = text[4:]
    return json.loads(text.strip())


def _import_topology_data(school, data: dict) -> tuple:
    """topology dict → NetworkDevice + NetworkLink 저장, (devices, links) 반환"""
    from .models import NetworkDevice, NetworkLink

    nodes = data.get('nodes', [])
    edges = data.get('edges', [])

    NetworkLink.objects.filter(from_device__school=school, link_type='manual').delete()
    NetworkDevice.objects.filter(school=school, ip_address__isnull=True, snmp_enabled=False).delete()

    CABLE_MAP = {'광': 'fiber', 'Cat6': 'cat6', 'Cat5e': 'cat5e', 'Cat5': 'cat5'}
    name_to_device = {}
    created_devices = 0
    for node in nodes:
        name = node.get('name', '').strip()
        if not name:
            continue
        dev, created = NetworkDevice.objects.get_or_create(
            school=school, name=name,
            defaults={
                'device_type':  node.get('device_type', 'switch'),
                'model':        node.get('model', ''),
                'location':     node.get('location', ''),
                'network_type': node.get('network_type', ''),
                'status':       'unknown',
            },
        )
        if created:
            created_devices += 1
        name_to_device[name] = dev

    created_links = 0
    for edge in edges:
        fd = name_to_device.get(edge.get('from', ''))
        td = name_to_device.get(edge.get('to', ''))
        if fd and td and fd != td:
            NetworkLink.objects.create(
                from_device=fd, to_device=td,
                link_type='manual', is_active=True,
                cable_type=CABLE_MAP.get(edge.get('cable_type', ''), 'unknown'),
                network_type=edge.get('network_type', ''),
            )
            created_links += 1

    return created_devices, created_links


@celery_app.task
def analyze_single_diagram(school_id: int, image_path: str):
    """단일 학교 구성도 이미지 분석 → 토폴로지 저장"""
    from apps.schools.models import School
    try:
        school = School.objects.get(id=school_id)
    except School.DoesNotExist:
        logger.error(f'School {school_id} not found')
        return {'status': 'error', 'message': '학교 없음'}

    try:
        data = _analyze_image_with_claude(image_path)
        devices, links = _import_topology_data(school, data)
        logger.info(f'[{school.name}] 장비 {devices}개, 링크 {links}개 등록')
        return {'status': 'ok', 'devices': devices, 'links': links}
    except Exception as e:
        logger.error(f'[{school.name}] 분석 오류: {e}')
        return {'status': 'error', 'message': str(e)}


@celery_app.task
def bulk_analyze_diagrams(image_dir: str = None):
    """구성도 이미지 폴더 전체 일괄 분석"""
    import django.core.cache as cache_module
    from apps.schools.models import School
    from django.core.cache import cache

    if image_dir is None:
        image_dir = os.path.join(os.environ.get('MEDIA_ROOT', '/app/media'), 'data', '구성도이미지')

    if not os.path.isdir(image_dir):
        logger.error(f'이미지 폴더 없음: {image_dir}')
        return

    # 학교명 → School 매핑
    school_map = {s.name: s for s in School.objects.all()}

    # 이미지 파일 목록 (구성도_학교명.jpg)
    files = sorted([
        f for f in os.listdir(image_dir)
        if f.lower().endswith(('.jpg', '.jpeg', '.png'))
    ])
    total = len(files)
    logger.info(f'일괄 분석 시작: {total}개 파일')

    progress = {
        'started': True, 'finished': False,
        'total': total, 'done': 0,
        'ok': 0, 'skip': 0, 'fail': 0,
        'results': [],
    }
    cache.set(BULK_DIAGRAM_KEY, progress, timeout=7200)

    for idx, filename in enumerate(files):
        # 파일명에서 학교명 추출: 구성도_가락고등학교.jpg → 가락고등학교
        school_name = filename
        for prefix in ('구성도_', '네트워크구성도_', '망구성도_'):
            if school_name.startswith(prefix):
                school_name = school_name[len(prefix):]
        school_name = os.path.splitext(school_name)[0]

        school = school_map.get(school_name)
        result_entry = {'school': school_name, 'file': filename}

        if not school:
            result_entry.update({'status': 'skip', 'note': 'DB 미등록 학교'})
            progress['skip'] += 1
            logger.warning(f'[{school_name}] DB에 없는 학교, 스킵')
        else:
            image_path = os.path.join(image_dir, filename)
            try:
                data = _analyze_image_with_claude(image_path)
                devices, links = _import_topology_data(school, data)
                result_entry.update({'status': 'ok', 'devices': devices, 'links': links})
                progress['ok'] += 1
                logger.info(f'[{school_name}] 완료: 장비 {devices}개, 링크 {links}개')
            except Exception as e:
                result_entry.update({'status': 'fail', 'note': str(e)[:80]})
                progress['fail'] += 1
                logger.error(f'[{school_name}] 실패: {e}')

        progress['done'] = idx + 1
        progress['results'].append(result_entry)
        # 최근 200건만 유지
        if len(progress['results']) > 200:
            progress['results'] = progress['results'][-200:]
        cache.set(BULK_DIAGRAM_KEY, progress, timeout=7200)

    progress['finished'] = True
    cache.set(BULK_DIAGRAM_KEY, progress, timeout=7200)
    logger.info(f'일괄 분석 완료: 성공 {progress["ok"]}, 스킵 {progress["skip"]}, 실패 {progress["fail"]}')
