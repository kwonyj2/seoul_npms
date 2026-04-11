"""
네트워크 서비스 – 토폴로지 빌드/저장
"""
from collections import defaultdict, deque

# ── 색상 테이블 ──────────────────────────────────────────────────
_NET_COLOR = {
    '교사망': '#0d6efd',
    '학생망': '#198754',
    '무선망': '#dc3545',
    '기타망': '#fd7e14',
    '전화망': '#6f42c1',
}
_TYPE_COLOR = {
    'firewall':   '#8b0000',
    'router':     '#fd7e14',
    'server':     '#6f42c1',
    'ap':         '#20c997',
    'poe_switch': '#0dcaf0',
    'switch':     '#0d6efd',
}
_CABLE_COLOR = {
    'fiber':   '#dc3545',
    'cat6':    '#0d6efd',
    'cat5e':   '#198754',
    'cat5':    '#6c757d',
    'unknown': '#adb5bd',
}
_CABLE_KO = {
    'fiber': '광', 'cat6': 'Cat6', 'cat5e': 'Cat5e', 'cat5': 'Cat5', 'unknown': '미확인'
}
_TYPE_LEVEL = {
    'firewall': 0, 'router': 1, 'server': 1,
    'switch': 2, 'poe_switch': 3, 'ap': 4,
}


def _compute_levels(devices, links):
    """링크 구조 BFS → 각 장비의 계층(level) 자동 계산"""
    all_ids  = {d.id for d in devices}
    children = defaultdict(list)
    has_parent = set()

    for lk in links:
        children[lk.from_device_id].append(lk.to_device_id)
        has_parent.add(lk.to_device_id)

    # 루트: 방화벽/라우터 우선, 없으면 incoming 없는 노드
    root_ids = {d.id for d in devices if d.device_type in ('firewall', 'router')}
    if not root_ids:
        root_ids = all_ids - has_parent
    if not root_ids:
        root_ids = all_ids

    levels = {}
    q = deque()
    for rid in root_ids:
        levels[rid] = 0
        q.append(rid)
    while q:
        nid = q.popleft()
        for cid in children[nid]:
            if cid not in levels:
                levels[cid] = levels[nid] + 1
                q.append(cid)

    # 링크 없는 고립 노드 → device_type 기반 fallback
    for d in devices:
        if d.id not in levels:
            levels[d.id] = _TYPE_LEVEL.get(d.device_type, 2)

    return levels


def build_topology_data(school_id: int) -> dict:
    """현재 DB 장비/링크 → vis.js 형식 토폴로지 반환"""
    from apps.network.models import NetworkDevice, NetworkLink

    devices = list(NetworkDevice.objects.filter(school_id=school_id))
    links   = list(NetworkLink.objects.filter(
        from_device__school_id=school_id, is_active=True
    ).select_related('from_device', 'to_device'))

    node_levels = _compute_levels(devices, links)

    nodes = []
    for d in devices:
        net    = d.network_type or ''
        color  = _NET_COLOR.get(net) or _TYPE_COLOR.get(d.device_type, '#0d6efd')
        border = '#dc3545' if d.status == 'down' else color
        is_root = d.device_type in ('firewall', 'router')
        level   = node_levels.get(d.id, _TYPE_LEVEL.get(d.device_type, 2))
        nodes.append({
            'id':          d.id,
            'label':       f'{d.name}\n{d.model or ""}',
            'title': (
                f'<b>{d.name}</b><br>'
                f'모델: {d.model or "-"}<br>'
                f'위치: {d.location or "-"}<br>'
                f'망: {net or "-"}<br>'
                f'IP: {d.ip_address or "미등록"}<br>'
                f'상태: {d.get_status_display()}'
            ),
            'color': {
                'background': color,
                'border':     border,
                'highlight':  {'background': color, 'border': '#000'},
            },
            'borderWidth': 3 if d.status == 'down' else (2 if is_root else 1),
            'font':  {'color': '#ffffff', 'size': 11},
            'size':  28 if is_root else 22,
            'shape': 'box',
            'level': level,
            # 필터·팝업용 메타
            'network_type': net,
            'device_type':  d.device_type,
            'ip_address':   d.ip_address or '',
            'status':       d.status,
            'model':        d.model or '',
            'location':     d.location or '',
        })

    edges = []
    for lk in links:
        cable     = lk.cable_type or 'unknown'
        from_net  = lk.from_device.network_type or ''
        clr       = _NET_COLOR.get(from_net) or _CABLE_COLOR.get(cable, '#adb5bd')
        dashes = False
        if cable == 'cat5e':
            dashes = [8, 4]
        elif cable == 'cat5':
            dashes = [3, 3]
        edges.append({
            'id':    lk.id,
            'from':  lk.from_device_id,
            'to':    lk.to_device_id,
            'color': {'color': clr, 'highlight': clr, 'opacity': 0.9},
            'width': 3 if cable == 'fiber' else 2,
            'dashes': dashes,
            'title': f'케이블: {_CABLE_KO.get(cable, cable)}<br>망: {lk.network_type or from_net or "-"}',
            'label': _CABLE_KO.get(cable, ''),
            'font':  {'size': 9, 'align': 'middle', 'color': '#444'},
            # 필터용 메타
            'cable_type':   cable,
            'network_type': lk.network_type or from_net,
        })

    return {'nodes': nodes, 'edges': edges}


def generate_and_save_topology(school_id: int):
    """현재 장비/링크를 NetworkTopology 스냅샷으로 저장"""
    from apps.network.models import NetworkTopology
    from apps.schools.models import School

    school = School.objects.get(id=school_id)
    data   = build_topology_data(school_id)
    return NetworkTopology.objects.create(school=school, topology_data=data)
