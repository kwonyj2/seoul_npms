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
    topo = NetworkTopology.objects.create(school=school, topology_data=data)
    try:
        write_topology_files_to_nas(school)
    except Exception:
        pass
    return topo


# ═══════════════════════════════════════════════════════
# NAS 파일 자동 생성 (토폴로지 CSV + SNMP 가이드 DOCX)
# ═══════════════════════════════════════════════════════

def _nas_topology_root():
    import os
    media = os.environ.get('NAS_MEDIA_ROOT', '/app/nas/media/npms')
    return os.path.join(media, '토폴로지')


def write_topology_csv(school, file_path: str):
    """장비 목록 CSV 생성"""
    import csv
    from apps.network.models import NetworkDevice
    TYPE_KO = {'switch':'스위치','poe_switch':'PoE스위치','ap':'무선AP','router':'라우터','firewall':'방화벽','server':'서버'}
    STATUS_KO = {'up':'정상','down':'장애','warning':'경고','unknown':'미확인'}
    devices = NetworkDevice.objects.filter(school=school).order_by('network_type', 'name')
    with open(file_path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(['장비명', '모델', '설치위치', '망구분', '장비유형', 'IP주소', '상태'])
        for d in devices:
            w.writerow([
                d.name, d.model, d.location, d.network_type,
                TYPE_KO.get(d.device_type, d.device_type),
                d.ip_address or '', STATUS_KO.get(d.status, d.status),
            ])


def write_snmp_guide_docx(school, file_path: str):
    """SNMP 가이드 DOCX 생성 (한글 폰트 적용)"""
    from docx import Document
    from docx.shared import Pt
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    from django.utils import timezone
    from apps.network.models import NetworkDevice

    KF = '맑은 고딕'
    doc = Document()

    def _setfont_style(st):
        st.font.name = KF
        rp = st.element.get_or_add_rPr()
        rf = rp.find(qn('w:rFonts'))
        if rf is None:
            rf = OxmlElement('w:rFonts'); rp.append(rf)
        for a in ('w:ascii','w:hAnsi','w:eastAsia','w:cs'):
            rf.set(qn(a), KF)

    _setfont_style(doc.styles['Normal'])
    doc.styles['Normal'].font.size = Pt(10)
    for hn in ('Heading 1','Heading 2','Heading 3','Title'):
        try:
            _setfont_style(doc.styles[hn])
        except KeyError:
            pass

    def _apply(r):
        r.font.name = KF
        rp = r._element.get_or_add_rPr()
        rf = rp.find(qn('w:rFonts'))
        if rf is None:
            rf = OxmlElement('w:rFonts'); rp.append(rf)
        for a in ('w:ascii','w:hAnsi','w:eastAsia','w:cs'):
            rf.set(qn(a), KF)

    def add_p(t, style=None):
        p = doc.add_paragraph(t, style=style) if style else doc.add_paragraph(t)
        for r in p.runs: _apply(r)
        return p

    def add_h(t, lvl):
        h = doc.add_heading(t, level=lvl)
        for r in h.runs: _apply(r)
        return h

    title = doc.add_heading(f'{school.name} SNMP 설정 가이드', 0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for r in title.runs: _apply(r)

    add_p(f'작성일: {timezone.now().strftime("%Y년 %m월 %d일")}')
    doc.add_paragraph()

    add_h('1. SNMP 개요', 1)
    add_p('SNMP(Simple Network Management Protocol)는 네트워크 장비의 상태를 모니터링하기 위한 표준 프로토콜입니다. '
          '본 시스템에서는 SNMPv2c를 사용하여 장비의 가동 상태, 트래픽, 포트 상태를 수집합니다.')

    add_h('2. 장비별 SNMP 설정 방법', 1)
    add_h('2-1. CBS/C3100/C3500 시리즈 (코어/분배 스위치)', 2)
    for cmd in ['snmp-server community public RO', 'snmp-server community private RW',
                'snmp-server enable traps', 'snmp-server host [NMS서버IP] traps public']:
        p = doc.add_paragraph(style='List Bullet')
        p.add_run(cmd).font.name = 'Courier New'

    add_h('2-2. GS724T / SG300 시리즈 (접속 스위치)', 2)
    add_p('웹 관리 인터페이스 접속 → Security → SNMP → Communities 메뉴에서 설정')
    for s in ['Community String: public (Read Only)', 'Trap Host: [NMS서버IP]', 'SNMP Version: v2c']:
        add_p(s, style='List Bullet')

    add_h('3. 장비 목록 및 설정 현황', 1)
    table = doc.add_table(rows=1, cols=6)
    table.style = 'Table Grid'
    hdr = table.rows[0].cells
    for i, h in enumerate(['장비명', '모델', '설치위치', '망구분', 'IP주소', 'SNMP']):
        hdr[i].text = h
        for r in hdr[i].paragraphs[0].runs:
            _apply(r); r.font.bold = True
    for d in NetworkDevice.objects.filter(school=school).order_by('network_type', 'name'):
        row = table.add_row().cells
        vals = [d.name, d.model or '-', d.location or '-', d.network_type or '-',
                d.ip_address or '미등록', '설정완료' if d.snmp_enabled else '미설정']
        for i, v in enumerate(vals):
            row[i].text = v
            for r in row[i].paragraphs[0].runs: _apply(r)

    add_h('4. NMS 연동 절차', 1)
    steps = ['장비에 SNMP Community String 설정 (public/private)',
             '장비 IP 주소를 NMS 시스템에 등록',
             '자산 관리 → 네트워크 설정 → SNMP 활성화 체크',
             'NMS 모니터링 탭에서 장비 상태 확인',
             '장애 발생 시 이벤트 알림 자동 수신']
    for i, s in enumerate(steps, 1):
        add_p(f'{i}. {s}')

    doc.save(file_path)


def write_topology_files_to_nas(school):
    """학교의 토폴로지 CSV + SNMP 가이드 DOCX를 NAS에 자동 생성
    저장 위치:
      /app/nas/media/npms/토폴로지/토폴로지/토폴로지_{학교명}_{YYYYMMDD}.csv
      /app/nas/media/npms/토폴로지/SNMP설정가이드/SNMP설정가이드_{학교명}_{YYYYMMDD}.docx
    """
    import os
    import logging
    from datetime import datetime
    log = logging.getLogger(__name__)
    root = _nas_topology_root()
    topo_dir = os.path.join(root, '토폴로지')
    snmp_dir = os.path.join(root, 'SNMP설정가이드')
    os.makedirs(topo_dir, exist_ok=True)
    os.makedirs(snmp_dir, exist_ok=True)
    today = datetime.now().strftime('%Y%m%d')
    csv_path = os.path.join(topo_dir, f'토폴로지_{school.name}_{today}.csv')
    docx_path = os.path.join(snmp_dir, f'SNMP설정가이드_{school.name}_{today}.docx')
    try:
        write_topology_csv(school, csv_path)
    except Exception as e:
        log.warning(f'[{school.name}] CSV 생성 실패: {e}')
    try:
        write_snmp_guide_docx(school, docx_path)
    except Exception as e:
        log.warning(f'[{school.name}] DOCX 생성 실패: {e}')
    return {'csv': csv_path, 'docx': docx_path}
