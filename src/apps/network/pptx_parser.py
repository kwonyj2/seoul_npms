"""
PowerPoint 네트워크 토폴로지 파서 (v2)
서울시교육청 표준 구성도 포맷 기반

명명 규칙:
  K#n = 교사망 스위치
  H#n = 학생망 스위치
  G#n = 기타망 스위치
  M#n = 무선망 백본
  P#n = POE 스위치 (무선 AP용)
  i#n = 전화망 스위치

포맷: "{코드} {모델명} {설치위치}"
예: "K#M E4020-24TX 신관 1층 전산실"
"""
import re
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Optional

NS = {
    'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
    'p': 'http://schemas.openxmlformats.org/presentationml/2006/main',
}

# ── 장비 코드 패턴 (교육청 표준) ─────────────────────────────────────────────
# K#M, H#1, P#12, M#BB, i#M, K# M (공백 허용), M # M 등
DEVICE_CODE_PAT = re.compile(
    r'^\s*([KHGMPi])\s*#\s*([A-Z0-9]+)\b',
    re.UNICODE
)
# 접두어 없는 버전: #M, #1, #BB 등 (네트워크 분류 라벨로 보완)
DEVICE_CODE_NOPREFIX_PAT = re.compile(
    r'^\s*#\s*([A-Z0-9]+)\b',
    re.UNICODE
)

# 네트워크 분류 라벨
NETWORK_LABEL_MAP = {
    '교사망': ('K', '교사망'),
    '학생망': ('H', '학생망'),
    '기타망': ('G', '기타망'),
    '무선망': ('M', '무선망'),
    '전화망': ('i', '전화망'),
}

# 계위 레이블
PHASE_PAT = re.compile(r'^(\d+)\s*계위\s*$')

# 연결 포트 정보 "(24←︎ 23)" 또는 "(1F←︎ UP1)"
PORT_PAT = re.compile(r'\(([^)]+?)[←↔]+\s*([^)]+?)\)')

# ── 코드 접두어 → 네트워크 유형 + 장비 유형 ─────────────────────────────────
PREFIX_MAP = {
    'K': ('교사망', 'l2_switch'),
    'H': ('학생망', 'l2_switch'),
    'G': ('기타망', 'l2_switch'),
    'M': ('무선망', 'l3_switch'),   # 백본
    'P': ('무선망', 'poe_switch'),
    'i': ('전화망', 'l2_switch'),
}

# ── 방화벽 키워드 ────────────────────────────────────────────────────────────
FIREWALL_KEYWORDS = ['방화벽', 'Firewall', 'FW', 'UTM']

# ── 노이즈 텍스트 (제외) ─────────────────────────────────────────────────────
NOISE_EXACT = {
    '광', 'Cat5', 'Cat5e', 'Cat6', '교사망', '학생망', '기타망', '무선망', '전화망',
    '범례', '계위', '연결포트', '업링크', '다운링크',
}


@dataclass
class Device:
    code: str = ''
    prefix: str = ''       # K, H, G, M, P, i
    suffix: str = ''       # M, 1, BB, 15 등
    name: str = ''
    model: str = ''
    location: str = ''
    device_type: str = ''
    network_type: str = ''
    phase: int = 0         # 1/2/3/4 계위
    x: int = 0
    y: int = 0
    raw_text: str = ''


@dataclass
class Port:
    """포트 연결 정보: (up_port ← down_port)"""
    up: str = ''       # 예: "UP1", "24", "3F"
    down: str = ''     # 예: "1", "23"
    device_code: str = ''


# ── 슬라이드 파싱 ────────────────────────────────────────────────────────────
def _tag(e):
    return e.tag.split('}')[-1] if '}' in e.tag else e.tag


def _get_text(sp):
    texts = [t.text for t in sp.findall('.//a:t', NS) if t.text]
    joined = ' '.join(texts)
    return re.sub(r'\s+', ' ', joined).strip()


def _get_position(sp):
    off = sp.find('.//a:off', NS)
    ext = sp.find('.//a:ext', NS)
    x = int(off.get('x', 0)) if off is not None else 0
    y = int(off.get('y', 0)) if off is not None else 0
    w = int(ext.get('cx', 0)) if ext is not None else 0
    h = int(ext.get('cy', 0)) if ext is not None else 0
    return x, y, w, h


def _get_line_color(sp):
    line = sp.find('.//a:ln', NS)
    if line is None:
        return ''
    clr = line.find('.//a:srgbClr', NS)
    if clr is not None:
        return clr.get('val', '').upper()
    return ''


# 망이름 포함 패턴 (예: "교사망 #M E4020-24TX 본관 4 층 방송실내 서버실")
NETWORK_NAME_DEVICE_PAT = re.compile(
    r'^\s*(교사망|학생망|기타망|무선망|전화망)\s*#\s*([A-Z0-9]+)\s+(.+)$',
    re.UNICODE
)
# POE 장비 (예: "POE#1 E4020-24PS 본관 4 층 방송실내 서버실")
POE_DEVICE_PAT = re.compile(r'^\s*POE\s*#\s*([A-Z0-9]+)\s+(.+)$', re.UNICODE)
# 백본 단축 (예: "BB# DSW2728XG 본관 4 층 방송실내 서버실")
BB_DEVICE_PAT = re.compile(r'^\s*BB\s*#\s+(.+)$', re.UNICODE)

# 범례용 텍스트 제외 (K#M~K#n, M#M~M#n P#n (POE) 등)
LEGEND_NOISE_PAT = re.compile(r'[KHGMPi]#[A-Z0-9]+\s*[~～]\s*[KHGMPi]#')

def _parse_device_text(text: str) -> Optional[Device]:
    """장비 텍스트 → Device

    지원 패턴:
    1. 'K#M E4020-24TX 신관 1층 전산실'         (표준 접두어)
    2. '교사망 #M E4020-24TX 본관 4 층 서버실'   (망이름 포함)
    3. 'POE#1 E4020-24PS 본관 4 층 서버실'     (POE 접두어)
    4. 'BB# DSW2728XG 본관 4 층 서버실'        (백본 단축)
    """
    # 범례 텍스트는 제외
    if LEGEND_NOISE_PAT.search(text):
        return None

    # 패턴 1: 표준
    m = DEVICE_CODE_PAT.match(text)
    if m:
        prefix = m.group(1)
        suffix = m.group(2)
        rest = text[m.end():].strip()
        parts = rest.split(None, 1)
        model = parts[0] if parts else ''
        location = parts[1].strip() if len(parts) > 1 else ''
        network_type, device_type = PREFIX_MAP.get(prefix, ('', 'l2_switch'))
        return Device(
            code=f'{prefix}#{suffix}', prefix=prefix, suffix=suffix,
            name=f'{prefix}#{suffix}', model=model, location=location,
            device_type=device_type, network_type=network_type, raw_text=text,
        )

    # 패턴 2: 망이름 포함 ("교사망 #M E4020-24TX")
    m = NETWORK_NAME_DEVICE_PAT.match(text)
    if m:
        net_label = m.group(1)
        suffix = m.group(2)
        rest = m.group(3).strip()
        parts = rest.split(None, 1)
        model = parts[0] if parts else ''
        location = parts[1].strip() if len(parts) > 1 else ''
        # 망이름 → 접두어 매핑
        label_to_prefix = {v[1]: k for k, (_, v) in [
            ('K', ('', '교사망')), ('H', ('', '학생망')),
            ('G', ('', '기타망')), ('M', ('', '무선망')), ('i', ('', '전화망'))
        ]}
        net_prefix_map = {'교사망': 'K', '학생망': 'H', '기타망': 'G', '무선망': 'M', '전화망': 'i'}
        prefix = net_prefix_map.get(net_label, 'K')
        network_type, device_type = PREFIX_MAP.get(prefix, ('', 'l2_switch'))
        return Device(
            code=f'{prefix}#{suffix}', prefix=prefix, suffix=suffix,
            name=f'{prefix}#{suffix}', model=model, location=location,
            device_type=device_type, network_type=network_type, raw_text=text,
        )

    # 패턴 3: POE 접두어
    m = POE_DEVICE_PAT.match(text)
    if m:
        suffix = m.group(1)
        rest = m.group(2).strip()
        parts = rest.split(None, 1)
        model = parts[0] if parts else ''
        location = parts[1].strip() if len(parts) > 1 else ''
        return Device(
            code=f'P#{suffix}', prefix='P', suffix=suffix,
            name=f'P#{suffix}', model=model, location=location,
            device_type='poe_switch', network_type='무선망', raw_text=text,
        )

    # 패턴 4: 백본 단축 (BB#)
    m = BB_DEVICE_PAT.match(text)
    if m:
        rest = m.group(1).strip()
        parts = rest.split(None, 1)
        model = parts[0] if parts else ''
        location = parts[1].strip() if len(parts) > 1 else ''
        return Device(
            code='M#BB', prefix='M', suffix='BB',
            name='M#BB', model=model, location=location,
            device_type='l3_switch', network_type='무선망', raw_text=text,
        )

    return None


def _parse_firewall_text(text: str) -> Optional[Device]:
    """방화벽 텍스트 파싱"""
    if not any(kw in text for kw in FIREWALL_KEYWORDS):
        return None

    # "방화벽 #1 Secui NGF800 신관 1층 전산실"
    # "TrusGuard 200E 10G 방화벽"
    # 모델명 추출 (알파벳+숫자 조합)
    m = re.search(r'\b([A-Z][A-Za-z0-9\-]{2,})', text)
    model = m.group(1) if m else ''

    # 위치
    loc_m = re.search(r'([가-힣A-Za-z]+관?\s*\d+\s*층?\s*[가-힣]*실?)', text)
    location = loc_m.group(1).strip() if loc_m else ''

    # 이름: "방화벽 #1" 또는 "방화벽"
    name_m = re.search(r'방화벽\s*#?\d*', text)
    name = name_m.group(0).strip() if name_m else '방화벽'

    return Device(
        name=name,
        code=name,
        model=model,
        location=location,
        device_type='firewall',
        network_type='',
        raw_text=text,
    )


def _extract_slide_title(root) -> str:
    """슬라이드 제목 추출 (첫 번째 의미있는 텍스트)"""
    for sp in root.findall('.//p:sp', NS):
        text = _get_text(sp)
        if text and len(text) >= 5 and ('구성도' in text or '네트워크' in text):
            # "가락고등학교 네트워크 구성도 (개선 후)" → "개선 후"
            m = re.search(r'\(([^)]+)\)', text)
            if m:
                return m.group(1).strip()
            return text[:50]
    return ''


def parse_pptx_topology(file_path: str) -> dict:
    """
    .pptx → {
        'nodes': [...],       # 통합 장비 목록
        'edges': [...],       # 통합 연결 목록
        'slides': [{          # 슬라이드별 정보
            'number': 1, 'title': '개선 후',
            'node_names': ['K#M', 'H#M', ...],
            'edge_keys': [['K#M', 'K#2'], ...],
        }],
        'stats': {...},
        'warnings': [...]
    }
    """
    all_devices = {}  # code → Device (중복 제거)
    all_firewalls = []
    slide_count = 0
    slide_info = []   # 슬라이드별 장비/링크 추적

    with zipfile.ZipFile(file_path, 'r') as z:
        slide_names = sorted([n for n in z.namelist()
                              if n.startswith('ppt/slides/slide') and n.endswith('.xml')])
        for idx, sname in enumerate(slide_names, 1):
            slide_count += 1
            xml_data = z.read(sname)
            root = ET.fromstring(xml_data)

            # 슬라이드 제목 추출
            slide_title = _extract_slide_title(root) or f'슬라이드 {idx}'
            slide_devs_this = set()
            current_phase = 0

            # ── 1차 수집: 네트워크 라벨 좌표, 접두어 없는 장비 후보 ──
            network_labels = []  # [(x, y, prefix, network_type), ...]
            noprefix_devices = []  # [(sp, x, y, text), ...]

            # 슬라이드 내 모든 텍스트박스 순회
            for sp in root.findall('.//p:sp', NS):
                text = _get_text(sp)
                if not text:
                    continue
                if text in NOISE_EXACT:
                    continue

                x, y, w, h = _get_position(sp)

                pm = PHASE_PAT.match(text)
                if pm:
                    current_phase = int(pm.group(1))
                    continue

                # 네트워크 분류 라벨 수집
                for lbl, (prefix, net_type) in NETWORK_LABEL_MAP.items():
                    if text.strip() == lbl:
                        network_labels.append((x, y, prefix, net_type))
                        break

                # 표준 장비 코드 (K#M, H#1 등)
                dev = _parse_device_text(text)
                if dev:
                    dev.x, dev.y = x, y
                    dev.phase = current_phase
                    slide_devs_this.add(dev.code)
                    if dev.code in all_devices:
                        existing = all_devices[dev.code]
                        if len(dev.raw_text) > len(existing.raw_text):
                            all_devices[dev.code] = dev
                    else:
                        all_devices[dev.code] = dev
                    continue

                # 접두어 없는 장비 코드 (#M, #1) → 나중에 라벨 매칭
                np_match = DEVICE_CODE_NOPREFIX_PAT.match(text)
                if np_match and not _parse_firewall_text(text):
                    noprefix_devices.append((sp, x, y, text))
                    continue

                fw = _parse_firewall_text(text)
                if fw:
                    fw.x, fw.y = x, y
                    fw.phase = current_phase or 1
                    slide_devs_this.add(fw.name)
                    dup = next((f for f in all_firewalls
                                if f.name == fw.name and f.location == fw.location), None)
                    if not dup:
                        all_firewalls.append(fw)

            # ── 2차: 접두어 없는 장비를 네트워크 라벨과 매칭 ──
            if noprefix_devices and network_labels:
                for sp, x, y, text in noprefix_devices:
                    # 가장 가까운 네트워크 라벨 찾기 (주로 위쪽에 위치)
                    best_label = None
                    best_dist = float('inf')
                    for lx, ly, prefix, net_type in network_labels:
                        # 수평 거리 작고 라벨이 위쪽(y가 작음)일수록 우선
                        dx = abs(x - lx)
                        dy = y - ly  # 양수 = 라벨이 위
                        # 라벨은 장비 위쪽에 있어야 함 (dy > 0)
                        if dy < 0:
                            continue
                        dist = dx + dy * 0.5  # 수평이 더 중요
                        if dist < best_dist:
                            best_dist = dist
                            best_label = (prefix, net_type)
                    if not best_label:
                        continue
                    # 접두어 붙여서 표준 파서로 처리
                    prefix, net_type = best_label
                    reconstructed = f'{prefix}{text.strip()}'
                    dev = _parse_device_text(reconstructed)
                    if dev:
                        dev.x, dev.y = x, y
                        dev.phase = current_phase
                        dev.raw_text = text
                        slide_devs_this.add(dev.code)
                        if dev.code not in all_devices:
                            all_devices[dev.code] = dev

            slide_info.append({
                'number': idx,
                'title': slide_title,
                'node_names': sorted(slide_devs_this),
            })

    # ── 엣지 추론 (계위 기반) ──
    # 현재는 포트 정보 기반 정확한 매칭이 어려우므로 "계위 연결" 방식:
    # N계위 백본 → N+1계위 분산 스위치 연결
    devices_list = list(all_devices.values())
    edges = []

    # 계위별 그룹화
    phase_groups = {}
    for d in devices_list:
        phase_groups.setdefault(d.phase, []).append(d)

    # ── 백본 판별 (3단계 완화) ──
    backbones = {}  # network_type → Device
    # 1순위: suffix가 'M', 'BB', 'BK', 'BKB' 등
    STANDARD_BACKBONE_SUFFIX = ('M', 'BB', 'BB1', 'BB2', 'BK', 'BKB', 'CORE')
    for d in devices_list:
        if d.suffix.upper() in STANDARD_BACKBONE_SUFFIX:
            if d.network_type not in backbones:
                backbones[d.network_type] = d

    # 2순위: 각 네트워크에서 번호가 가장 낮은 장비를 백본으로
    # (K#1, H#1 등이 실질적 백본인 케이스)
    def _suffix_num(s):
        """'1' → 1, '01' → 1, 'BB' → 9999"""
        m = re.match(r'^0*(\d+)$', s)
        return int(m.group(1)) if m else 9999

    for d in devices_list:
        if d.network_type in backbones:
            continue
        # 같은 네트워크에서 번호 있는 장비 중 가장 작은 번호 찾기
        same_net = [x for x in devices_list
                    if x.network_type == d.network_type and re.match(r'^0*\d+$', x.suffix)]
        if same_net:
            lowest = min(same_net, key=lambda x: _suffix_num(x.suffix))
            backbones[d.network_type] = lowest

    # ── 분산 스위치 → 백본 연결 ──
    for d in devices_list:
        backbone = backbones.get(d.network_type)
        if backbone and backbone != d:
            edges.append({
                'from_name': backbone.code,
                'to_name': d.code,
                'network_type': d.network_type,
                'cable_type': 'fiber' if d.prefix in ('K', 'H') else 'cat6',
                'inferred': True,
            })

    # ── 3순위: 백본이 없는 네트워크는 방화벽 → 모든 분산 직결 ──
    if all_firewalls:
        fw = all_firewalls[0]
        connected_via_backbone = {(e['from_name'], e['to_name']) for e in edges}
        for d in devices_list:
            # 해당 네트워크에 백본이 없는 경우만
            if d.network_type not in backbones:
                if (fw.name, d.code) not in connected_via_backbone:
                    edges.append({
                        'from_name': fw.name,
                        'to_name': d.code,
                        'network_type': d.network_type,
                        'cable_type': 'fiber',
                        'inferred': True,
                    })

    # 1계위 방화벽 → 2계위 백본 연결
    if all_firewalls and backbones:
        fw = all_firewalls[0]
        for bb in backbones.values():
            edges.append({
                'from_name': fw.name,
                'to_name': bb.code,
                'network_type': bb.network_type,
                'cable_type': 'fiber',
                'inferred': True,
            })

    # ── 결과 정리 ──
    nodes = []
    for d in devices_list + all_firewalls:
        nodes.append({
            'name': d.code if d.code else d.name,
            'device_type': d.device_type,
            'model': d.model,
            'location': d.location,
            'network_type': d.network_type,
            'phase': d.phase,
        })

    warnings = []
    if not nodes:
        warnings.append('장비가 하나도 인식되지 않았습니다.')
    if devices_list and not backbones:
        warnings.append('2계위 백본 장비(K#M, H#M 등)를 찾지 못해 연결 추론 실패.')

    # 슬라이드별 엣지 필터 (각 슬라이드에 속하는 노드 간 연결만)
    for si in slide_info:
        node_set = set(si['node_names'])
        # 방화벽도 포함 (첫 번째 슬라이드에만)
        if si['number'] == 1:
            for fw in all_firewalls:
                node_set.add(fw.name)
        si['edge_keys'] = [
            [e['from_name'], e['to_name']]
            for e in edges
            if e['from_name'] in node_set and e['to_name'] in node_set
        ]

    return {
        'nodes': nodes,
        'edges': edges,
        'slides': slide_info,
        'stats': {
            'slides': slide_count,
            'devices_found': len(devices_list),
            'firewalls_found': len(all_firewalls),
            'backbones_found': len(backbones),
            'edges_inferred': len(edges),
        },
        'warnings': warnings,
    }
