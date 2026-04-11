"""
network 비즈니스 로직
네트워크 토폴로지 자동생성 서비스
"""
from .models import NetworkDevice, NetworkLink, NetworkTopology


# 장비 유형별 Vis.js 노드 색상/아이콘
DEVICE_STYLE = {
    'switch':     {'color': '#0d6efd', 'shape': 'box',     'icon': '🔀'},
    'poe_switch': {'color': '#0dcaf0', 'shape': 'box',     'icon': '⚡'},
    'ap':         {'color': '#198754', 'shape': 'ellipse', 'icon': '📶'},
    'router':     {'color': '#fd7e14', 'shape': 'diamond', 'icon': '🌐'},
    'firewall':   {'color': '#dc3545', 'shape': 'triangle','icon': '🔥'},
    'server':     {'color': '#6f42c1', 'shape': 'box',     'icon': '🖥'},
}

# 계층형 트리 레이아웃 레벨 (위→아래: 방화벽→라우터→스위치→PoE→AP)
DEVICE_LEVEL = {
    'firewall':   0,
    'router':     1,
    'server':     1,
    'switch':     2,
    'poe_switch': 3,
    'ap':         4,
}

STATUS_BORDER = {
    'up':      '#198754',
    'down':    '#dc3545',
    'warning': '#ffc107',
    'unknown': '#adb5bd',
}


def build_topology_data(school_id: int) -> dict:
    """
    학교의 NetworkDevice + NetworkLink 데이터로 Vis.js 형식 토폴로지 생성
    반환: {"nodes": [...], "edges": [...]}
    """
    devices = NetworkDevice.objects.filter(school_id=school_id).select_related('school')
    links   = NetworkLink.objects.filter(
        from_device__school_id=school_id,
        is_active=True,
    ).select_related('from_device', 'to_device', 'from_port', 'to_port')

    nodes = []
    for dev in devices:
        style  = DEVICE_STYLE.get(dev.device_type, {'color': '#6c757d', 'shape': 'box', 'icon': '📦'})
        border = STATUS_BORDER.get(dev.status, '#adb5bd')
        label  = f"{dev.name}\n{dev.ip_address or ''}"
        title  = (
            f"<b>{dev.name}</b><br>"
            f"IP: {dev.ip_address or '-'}<br>"
            f"유형: {dev.get_device_type_display()}<br>"
            f"상태: {dev.get_status_display()}<br>"
            f"MAC: {dev.mac_address or '-'}<br>"
            f"위치: {dev.location or '-'}"
        )
        nodes.append({
            'id':    dev.pk,
            'label': label,
            'title': title,
            'shape': style['shape'],
            'color': {
                'background': style['color'],
                'border':     border,
                'highlight':  {'background': style['color'], 'border': '#000'},
            },
            'font': {'color': '#fff', 'size': 11},
            'borderWidth': 3 if dev.status == 'down' else 1,
            'level':       DEVICE_LEVEL.get(dev.device_type, 2),
            'device_type': dev.device_type,
            'status':      dev.status,
            'ip_address':  dev.ip_address,
            'model':       dev.model or '',
            'location':    dev.location or '',
            'network_type': dev.network_type or '',
        })

    edges = []
    for link in links:
        edge_color = '#198754' if link.from_device.status == 'up' and link.to_device.status == 'up' else '#dc3545'
        from_port  = link.from_port.port_name or f"P{link.from_port.port_num}" if link.from_port else ''
        to_port    = link.to_port.port_name   or f"P{link.to_port.port_num}"   if link.to_port   else ''
        speed_label= f"{link.speed_mbps}M" if link.speed_mbps else ''
        label      = speed_label or link.link_type.upper()
        title      = (
            f"<b>{link.from_device.name}</b> {from_port} ↔ "
            f"<b>{link.to_device.name}</b> {to_port}<br>"
            f"방식: {link.get_link_type_display()}<br>"
            f"속도: {link.speed_mbps or '-'} Mbps"
        )
        edges.append({
            'id':    link.pk,
            'from':  link.from_device_id,
            'to':    link.to_device_id,
            'label': label,
            'title': title,
            'color': {'color': edge_color, 'highlight': edge_color},
            'width': 2 if link.speed_mbps and link.speed_mbps >= 1000 else 1,
            'dashes': link.link_type == 'manual',
        })

    return {'nodes': nodes, 'edges': edges}


def generate_and_save_topology(school_id: int) -> NetworkTopology:
    """토폴로지 생성 후 DB 스냅샷 저장"""
    data = build_topology_data(school_id)
    from apps.schools.models import School
    school = School.objects.get(pk=school_id)
    topo = NetworkTopology.objects.create(school=school, topology_data=data)
    return topo
