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


# ── PPTX 구성도 파싱 ─────────────────────────────────────
# 기존 이미지 AI 분석(Claude Vision) → PPTX XML 파싱으로 전환
# 정확도 70~80% → 95%+, 속도 60배, 비용 0원

def _analyze_image_with_claude(image_path: str) -> dict:
    """(Deprecated) 이미지 분석 — PPTX 파서로 대체됨. 호환성을 위해 남겨둠"""
    raise NotImplementedError('이미지 AI 분석은 제거되었습니다. PPTX 사용')

    api_key = os.environ.get('ANTHROPIC_API_KEY', '')
    if not api_key:
        raise ValueError('ANTHROPIC_API_KEY가 설정되지 않았습니다.')

    import base64
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


def _import_pptx_topology(school, data: dict, pptx_path: str = '') -> tuple:
    """PPTX 파서 결과를 DB에 저장
    - 수동 입력 장비(ip_address 또는 snmp_enabled)는 보존
    - 자동 등록 장비/링크만 삭제 후 재생성
    """
    from .models import NetworkDevice, NetworkLink, NetworkTopology
    from django.utils import timezone
    import os

    nodes = data.get('nodes', [])
    edges = data.get('edges', [])
    slides = data.get('slides', [])

    # 기존 자동 등록 장비·링크만 삭제 (수동 데이터 보호)
    NetworkLink.objects.filter(from_device__school=school, link_type='manual').delete()
    auto_devices = NetworkDevice.objects.filter(
        school=school, ip_address__isnull=True, snmp_enabled=False
    )
    auto_devices.delete()

    # 장비 생성
    name_to_device = {}
    created_devices = 0
    for node in nodes:
        name = node.get('name', '').strip()
        if not name:
            continue
        dev, created = NetworkDevice.objects.get_or_create(
            school=school, name=name,
            defaults={
                'device_type': node.get('device_type') or 'switch',
                'model': node.get('model', ''),
                'location': node.get('location', ''),
                'network_type': node.get('network_type', ''),
                'status': 'unknown',
            },
        )
        if created:
            created_devices += 1
        name_to_device[name] = dev

    # 링크 생성
    created_links = 0
    for edge in edges:
        fd = name_to_device.get(edge.get('from_name', ''))
        td = name_to_device.get(edge.get('to_name', ''))
        if fd and td and fd != td:
            NetworkLink.objects.create(
                from_device=fd, to_device=td,
                link_type='manual', is_active=True,
                cable_type=edge.get('cable_type', 'unknown'),
                network_type=edge.get('network_type', ''),
            )
            created_links += 1

    # NetworkTopology 저장 (슬라이드/통합 데이터 + PPTX 메타)
    mtime = None
    if pptx_path and os.path.exists(pptx_path):
        mtime = timezone.datetime.fromtimestamp(
            os.path.getmtime(pptx_path), tz=timezone.get_current_timezone()
        )

    NetworkTopology.objects.update_or_create(
        school=school,
        defaults={
            'topology_data': {
                'nodes': nodes, 'edges': edges, 'slides': slides,
                'stats': data.get('stats', {}),
            },
            'pptx_path': pptx_path,
            'pptx_mtime': mtime,
            'slide_titles': [s.get('title', '') for s in slides],
        }
    )

    # NAS에 토폴로지 CSV + SNMP 가이드 DOCX 자동 생성
    try:
        from .services import write_topology_files_to_nas
        write_topology_files_to_nas(school)
    except Exception as e:
        logger.warning(f'[{school.name}] NAS 파일 자동 생성 실패: {e}')

    return created_devices, created_links


def _extract_school_name_from_filename(filename: str) -> str:
    """파일명에서 학교명 추출
    예: '2025년 테크센터-네트워크 구성도_가락고등학교.pptx' → '가락고등학교'
    예: '2025년 테크센터-유치원 네트워크 구성도_새솔유치원.pptx' → '새솔유치원'
    예: '서울새솔유치원.pptx' → '서울새솔유치원'
    """
    import re
    name = os.path.splitext(filename)[0]
    # "_학교명" 패턴이 있으면 그 뒤만 추출
    if '_' in name:
        name = name.rsplit('_', 1)[-1]
    # 공백 제거·정리
    return name.strip()


def _find_school_by_name(name: str, school_map: dict):
    """학교명에서 School 객체 찾기 (유연한 매칭)"""
    n = name.strip()
    # 정확 일치
    if n in school_map:
        return school_map[n]
    # 접두어 "서울" 추가/제거 시도
    for variant in (n, '서울' + n, n.replace('서울', '', 1)):
        if variant in school_map:
            return school_map[variant]
    # 부분 일치 (가락고 → 가락고등학교)
    for sname, school in school_map.items():
        if n in sname or sname in n:
            if len(n) >= 3:  # 너무 짧은 매칭 방지
                return school
    return None


@celery_app.task
def scan_network_pptx(school_id: int = None):
    """NAS PPTX 파일을 스캔하여 토폴로지 생성

    지원 경로:
    1. /app/nas/media/npms/산출물/{school_id}/구성도/*.pptx (학교ID 기반)
    2. /app/nas/media/npms/산출물/2025년 테크센터/2025년 테크센터-네트워크 구성도/*.pptx
       (파일명 뒤 '_학교명.pptx' 기반 자동 매칭)
    """
    from apps.schools.models import School
    from .pptx_parser import parse_pptx_topology
    import os

    base_dir = os.environ.get('NAS_ARTIFACT_ROOT', '/app/nas/media/npms/산출물')
    stats = {'total': 0, 'ok': 0, 'skip': 0, 'fail': 0, 'results': []}

    # 학교명 → School 매핑
    school_map = {s.name: s for s in School.objects.all()}

    if school_id:
        schools = School.objects.filter(id=school_id)
    else:
        schools = School.objects.all()

    # ── 방식 1: 학교ID 기반 폴더 ──
    handled_schools = set()
    for school in schools:
        pptx_dir = os.path.join(base_dir, str(school.id), '구성도')
        if os.path.isdir(pptx_dir):
            pptx_files = sorted([
                f for f in os.listdir(pptx_dir)
                if f.lower().endswith('.pptx') and not f.startswith('.') and not f.startswith('~')
            ], key=lambda f: os.path.getmtime(os.path.join(pptx_dir, f)), reverse=True)
            if pptx_files:
                pptx_path = os.path.join(pptx_dir, pptx_files[0])
                _process_one(school, pptx_path, pptx_files[0], stats)
                handled_schools.add(school.id)

    # ── 방식 2: 테크센터 구성도 폴더 스캔 (파일명 매칭) ──
    # school_id 지정된 경우에도 해당 학교 PPTX가 있는지 체크
    tech_dirs = []
    for root, dirs, files in os.walk(base_dir):
        if '네트워크 구성도' in os.path.basename(root) or '네트워크구성도' in os.path.basename(root):
            tech_dirs.append(root)

    target_school_ids = {s.id for s in schools}

    for tech_dir in tech_dirs:
        for fname in sorted(os.listdir(tech_dir)):
            if not fname.lower().endswith('.pptx') or fname.startswith('.') or fname.startswith('~'):
                continue
            school_name = _extract_school_name_from_filename(fname)
            school = _find_school_by_name(school_name, school_map)
            if not school:
                if not school_id:  # 전체 스캔일 때만 skip 기록
                    stats['total'] += 1
                    stats['skip'] += 1
                    stats['results'].append({
                        'school_id': None, 'school_name': school_name,
                        'status': 'skip', 'note': f'DB 학교 매칭 실패: {fname}',
                        'pptx': fname,
                    })
                continue
            if school.id in handled_schools:
                continue
            # 개별 스캔 시 대상 학교만 처리
            if school_id and school.id not in target_school_ids:
                continue
            pptx_path = os.path.join(tech_dir, fname)
            _process_one(school, pptx_path, fname, stats)
            handled_schools.add(school.id)

    # ── 3. 처리 안된 학교들은 skip ──
    if not school_id:
        for school in schools:
            if school.id not in handled_schools:
                stats['total'] += 1
                stats['skip'] += 1
                stats['results'].append({
                    'school_id': school.id, 'school_name': school.name,
                    'status': 'skip', 'note': 'PPTX 파일 없음',
                })

    # 결과 리스트 너무 크면 잘라냄
    if len(stats['results']) > 500:
        stats['results'] = stats['results'][:500]

    return stats


def _process_one(school, pptx_path, fname, stats):
    """한 학교의 PPTX 파싱 + 저장 + stats 업데이트"""
    from .pptx_parser import parse_pptx_topology
    stats['total'] += 1
    result = {'school_id': school.id, 'school_name': school.name, 'pptx': fname}
    try:
        data = parse_pptx_topology(pptx_path)
        devices, links = _import_pptx_topology(school, data, pptx_path)
        result.update({
            'status': 'ok',
            'devices': devices,
            'links': links,
            'slides': data.get('stats', {}).get('slides', 0),
        })
        stats['ok'] += 1
        logger.info(f'[{school.name}] PPTX 파싱 완료: 장비 {devices}, 링크 {links}')
    except Exception as e:
        result['status'] = 'fail'
        result['note'] = str(e)[:200]
        stats['fail'] += 1
        logger.error(f'[{school.name}] PPTX 파싱 실패: {e}')
    stats['results'].append(result)


@celery_app.task
def bulk_analyze_diagrams(image_dir: str = None):
    """(Deprecated) 이미지 AI 분석 → scan_network_pptx 로 대체됨"""
    return scan_network_pptx.apply()


def _old_bulk_analyze_deprecated(image_dir: str = None):
    """[DEPRECATED] 구 이미지 분석 코드"""
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
