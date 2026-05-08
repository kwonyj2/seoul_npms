"""
PPTX 네트워크 구성도 일괄 추출기
================================
폴더의 모든 PPTX 파일에서 네트워크 장비 정보를 추출하여
학교명 컬럼이 추가된 단일 엑셀 파일을 생성합니다.

원본: 구성도정보추출기.txt (AI 어시스턴트 추출 파이프라인)
포트 정규식 확장 적용 (유니코드 화살표 ←︎↔︎ 등)
"""
import math
import re
import tempfile
import zipfile
from collections import defaultdict
from pathlib import Path
from xml.etree import ElementTree as ET


# ===========================================================================
# 상수
# ===========================================================================
NS = {
    'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
    'p': 'http://schemas.openxmlformats.org/presentationml/2006/main',
}
EMU = 914400
DEVICE_ID_RE = re.compile(r'^(Secui|TrusGuard|[KHMGPi]#)')
# 포트 정규식 확장: (1←︎23), (3F←︎UP1), (UP2←︎25), (2↔︎7) 등
PORT_RE = re.compile(r'^\(([A-Za-z0-9]+)\s*[←→↔︎\u2190-\u21FF\uFE00-\uFE0F\-~]+\s*([A-Za-z0-9]+)\)$')

CABLE_COLOR_MAP = {
    'FF0000': '광',
    '00AFEF': 'Cat6',
    '00B0F0': 'Cat6',
    '00B050': 'Cat5',
    'FF66CC': 'Cat5e',
}


# ===========================================================================
# 학교명 추출
# ===========================================================================
def extract_school_name(pptx_path):
    p = Path(pptx_path)
    candidates = [p.stem, p.parent.name]
    for cand in candidates:
        m = re.search(r'([가-힣]{2,}?(?:초등학교|중학교|고등학교|특수학교|학교|유치원))', cand)
        if m:
            return m.group(1)
    for cand in candidates:
        parts = re.split(r'[_\-\s\.]+', cand)
        for token in reversed(parts):
            if re.search(r'[가-힣]{2,}', token):
                return token
    return p.stem


# ===========================================================================
# PPTX 파싱
# ===========================================================================
def get_xfrm(spPr):
    xfrm = spPr.find('a:xfrm', NS)
    if xfrm is None:
        return None
    off = xfrm.find('a:off', NS)
    ext = xfrm.find('a:ext', NS)
    chOff = xfrm.find('a:chOff', NS)
    chExt = xfrm.find('a:chExt', NS)
    return {
        'x': int(off.get('x')) if off is not None else 0,
        'y': int(off.get('y')) if off is not None else 0,
        'w': int(ext.get('cx')) if ext is not None else 0,
        'h': int(ext.get('cy')) if ext is not None else 0,
        'chX': int(chOff.get('x')) if chOff is not None else 0,
        'chY': int(chOff.get('y')) if chOff is not None else 0,
        'chW': int(chExt.get('cx')) if chExt is not None else 0,
        'chH': int(chExt.get('cy')) if chExt is not None else 0,
        'flipH': xfrm.get('flipH', '0'),
        'flipV': xfrm.get('flipV', '0'),
    }


def walk_shapes(slide_root):
    """슬라이드의 모든 도형을 순회하며 텍스트 도형과 라인을 분리해서 반환.
    그룹의 변환 행렬을 누적 적용하여 절대 좌표를 계산.
    """
    text_shapes = []
    lines = []

    def _walk(elem, ax, ay, sx, sy):
        for child in elem:
            tag = child.tag.split('}')[-1]
            if tag == 'grpSp':
                grpSpPr = child.find('p:grpSpPr', NS)
                if grpSpPr is None:
                    _walk(child, ax, ay, sx, sy)
                    continue
                xf = get_xfrm(grpSpPr)
                if xf is None or not xf['chW'] or not xf['chH']:
                    _walk(child, ax, ay, sx, sy)
                    continue
                new_sx = sx * (xf['w'] / xf['chW'])
                new_sy = sy * (xf['h'] / xf['chH'])
                new_ax = ax + xf['x'] * sx - xf['chX'] * new_sx
                new_ay = ay + xf['y'] * sy - xf['chY'] * new_sy
                _walk(child, new_ax, new_ay, new_sx, new_sy)
            elif tag in ('sp', 'cxnSp'):
                spPr = child.find('p:spPr', NS)
                if spPr is None:
                    continue
                xf = get_xfrm(spPr)
                if xf is None:
                    continue

                abs_x = (ax + xf['x'] * sx) / EMU
                abs_y = (ay + xf['y'] * sy) / EMU
                abs_w = xf['w'] * sx / EMU
                abs_h = xf['h'] * sy / EMU

                ln = spPr.find('a:ln', NS)
                color, dash = None, 'solid'
                if ln is not None:
                    srgb = ln.find('.//a:srgbClr', NS)
                    if srgb is not None:
                        color = srgb.get('val')
                    d = ln.find('a:prstDash', NS)
                    if d is not None:
                        dash = d.get('val')

                prst = spPr.find('a:prstGeom', NS)
                cust = spPr.find('a:custGeom', NS)
                geom = (prst.get('prst') if prst is not None
                        else 'custom' if cust is not None else 'unknown')

                paras = []
                txBody = child.find('p:txBody', NS)
                if txBody is not None:
                    for p in txBody.findall('a:p', NS):
                        t = ''.join(r.text or '' for r in p.findall('.//a:t', NS)).strip()
                        if t:
                            paras.append(t)

                is_line = (tag == 'cxnSp' or geom == 'line'
                           or (geom == 'custom' and color is not None and ln is not None))

                entry = {
                    'x': abs_x, 'y': abs_y, 'w': abs_w, 'h': abs_h,
                    'cx': abs_x + abs_w / 2, 'cy': abs_y + abs_h / 2,
                    'flipH': xf['flipH'], 'flipV': xf['flipV'],
                    'color': color, 'dash': dash, 'geom': geom, 'paras': paras,
                }

                if is_line and cust is not None:
                    pathEl = cust.find('.//a:path', NS)
                    if pathEl is not None:
                        pw = int(pathEl.get('w', 0))
                        ph = int(pathEl.get('h', 0))
                        pts = []
                        for c2 in pathEl:
                            ttag = c2.tag.split('}')[-1]
                            for pt in c2.findall('a:pt', NS):
                                pts.append((ttag, int(pt.get('x')), int(pt.get('y'))))
                        entry['pts_local'] = pts
                        entry['pw'] = pw
                        entry['ph'] = ph

                if is_line:
                    lines.append(entry)
                elif paras:
                    text_shapes.append(entry)

    spTree = slide_root.find('.//p:cSld/p:spTree', NS)
    if spTree is not None:
        _walk(spTree, 0, 0, 1.0, 1.0)
    return text_shapes, lines


def line_endpoints(l):
    if l.get('pts_local') and l.get('pw') and l.get('ph'):
        first, last = l['pts_local'][0], l['pts_local'][-1]
        x1 = l['x'] + (first[1] / l['pw']) * l['w']
        y1 = l['y'] + (first[2] / l['ph']) * l['h']
        x2 = l['x'] + (last[1] / l['pw']) * l['w']
        y2 = l['y'] + (last[2] / l['ph']) * l['h']
        return x1, y1, x2, y2
    x1, y1, x2, y2 = l['x'], l['y'], l['x'] + l['w'], l['y'] + l['h']
    if l['flipH'] == '1':
        x1, x2 = x2, x1
    if l['flipV'] == '1':
        y1, y2 = y2, y1
    return x1, y1, x2, y2


# ===========================================================================
# 장비/포트 분리
# ===========================================================================
def extract_short_id(text):
    m = re.match(r'(Secui\s*\d+ED\s*#\d+|TrusGuard\s*\w+|[KHMGPi]#\s*[A-Z0-9]+)',
                 re.sub(r'\s+', ' ', text).strip())
    return re.sub(r'\s+', '', m.group(1)) if m else text[:10]


def extract_devices_and_ports(text_shapes):
    devices, port_labels = [], []
    for s in text_shapes:
        paras = s['paras']
        if not paras:
            continue
        if len(paras) == 1 and PORT_RE.match(paras[0]):
            m = PORT_RE.match(paras[0])
            port_labels.append({
                'p1': m.group(1), 'p2': m.group(2),
                'cx': s['cx'], 'cy': s['cy'], 'src': 'standalone',
            })
        elif DEVICE_ID_RE.match(paras[0]):
            paras_clean = paras[:]
            if len(paras) >= 3 and PORT_RE.match(paras[-1]):
                m = PORT_RE.match(paras[-1])
                port_labels.append({
                    'p1': m.group(1), 'p2': m.group(2),
                    'cx': s['cx'], 'cy': s['y'] + s['h'] - 0.05,
                    'src': 'belongs_to_below',
                })
                paras_clean = paras[:-1]
            devices.append({
                'x': s['x'], 'y': s['y'], 'w': s['w'], 'h': s['h'],
                'cx': s['cx'], 'cy': s['cy'], 'paras_clean': paras_clean,
            })

    for d in devices:
        d['short'] = extract_short_id(d['paras_clean'][0])
    return devices, port_labels


def match_ports_to_devices(devices, port_labels):
    used = set()
    for d in sorted(devices, key=lambda x: (x['cy'], x['cx'])):
        best, best_score = None, 999
        for i, pl in enumerate(port_labels):
            if i in used or pl['cy'] >= d['y']:
                continue
            dx = abs(pl['cx'] - d['cx'])
            dy = d['y'] - pl['cy']
            if dx > d['w'] / 2 + 0.3 or dy > 0.8:
                continue
            score = dy + dx * 0.4
            if score < best_score:
                best_score, best = score, i
        if best is not None:
            pl = port_labels[best]
            d['port'] = (pl['p1'], pl['p2'])
            used.add(best)
        else:
            d['port'] = None


# ===========================================================================
# 케이블 라인 → 엣지 매칭
# ===========================================================================
def extract_edges(lines, devices):
    edge_cable = {}

    def nearest_device(x, y, max_dist=1.2):
        best, best_d = None, max_dist
        for d in devices:
            dx = max(0, abs(x - d['cx']) - d['w'] / 2)
            dy = max(0, abs(y - d['cy']) - d['h'] / 2)
            dist = math.hypot(dx, dy)
            if dist < best_d:
                best_d, best = dist, d
        return best

    for l in lines:
        if not l.get('color'):
            continue
        cable = CABLE_COLOR_MAP.get(l['color'])
        if not cable:
            continue
        x1, y1, x2, y2 = line_endpoints(l)
        if y1 < 1.3 and y2 < 1.3 and l['w'] < 0.5:
            continue
        if l['dash'] == 'sysDash' and l['color'] == 'FF66CC':
            cable = 'Cat5e'

        a = nearest_device(x1, y1)
        b = nearest_device(x2, y2)
        if a and b and a['short'] != b['short']:
            edge_cable[(a['short'], b['short'])] = cable
            edge_cable[(b['short'], a['short'])] = cable

    return edge_cable


# ===========================================================================
# 메타데이터 파싱 + 토폴로지 결정
# ===========================================================================
def net_from_id(sid):
    if sid.startswith('K#'): return '교사망'
    if sid.startswith('H#'): return '학생망'
    if sid.startswith('M#') or sid.startswith('P#'): return '무선망'
    if sid.startswith('G#'): return '기타망'
    return '보안(공통)'


def tier_from_y(cy):
    if cy < 1.6: return '상단(보안)'
    if cy < 2.9: return '1계위'
    if cy < 5.9: return '2계위'
    return '3계위'


def parse_meta(d):
    paras = d.get('paras_clean', [])
    p0 = paras[0] if paras else ''
    p1 = paras[1] if len(paras) > 1 else ''
    short = d['short']

    if short.startswith('Secui'):
        return 'Secui 800ED', '본관', '1F', '방화벽'
    if short.startswith('TrusGuard'):
        return 'TrusGuard 200E', '본관', '1F', '10G 방화벽'

    model = p0.replace(short, '', 1).strip()
    building = floor = location = ''
    if p1:
        bm = re.search(r'(본관|정보관|정보동|체육관|별관|학생관|학생동|신관|후관|동관)', p1)
        if bm:
            building = bm.group(1)
        fm = re.search(r'(\d+)\s*[F층]', p1)
        if fm:
            floor = f"{fm.group(1)}F"
        rest = p1
        if bm: rest = rest.replace(bm.group(0), '', 1)
        if fm: rest = rest.replace(fm.group(0), '', 1)
        location = re.sub(r'\s+', ' ', rest).strip()
    return model, building, floor, location


def resolve_upper(d, devices, edge_cable):
    short = d['short']
    network = net_from_id(short)
    tier = tier_from_y(d['cy'])
    short_to_dev = {x['short']: x for x in devices}

    if tier == '상단(보안)':
        return None, None

    if tier == '1계위':
        for (a, b), cable in edge_cable.items():
            if a == short:
                other = short_to_dev.get(b)
                if other and other['cy'] < d['cy'] - 0.3:
                    return other, cable
        return None, None

    if tier == '3계위':
        cands = [c for c in devices
                 if c['cy'] < d['cy'] - 0.3
                 and tier_from_y(c['cy']) == '2계위'
                 and net_from_id(c['short']) == network]
        if cands:
            cands.sort(key=lambda c: abs(c['cx'] - d['cx']))
            target = cands[0]
            return target, edge_cable.get((short, target['short']))
        return None, None

    # 2계위
    cores = {'교사망': 'K#M', '학생망': 'H#M', '기타망': 'G#M'}
    if network in cores and cores[network] in short_to_dev:
        target = cores[network]
        return short_to_dev[target], edge_cable.get((short, target))

    if network == '무선망':
        if short.startswith('P#'):
            for (a, b), cable in edge_cable.items():
                if a == short:
                    other = short_to_dev.get(b)
                    if other and other['cy'] < d['cy'] - 0.3:
                        return other, cable
            return short_to_dev.get('G#M'), None
        if short.startswith('M#'):
            return short_to_dev.get('M#BB'), edge_cable.get((short, 'M#BB'))

    return None, None


def infer_cable(d, upper, devices):
    p = d.get('port')
    if not p and not upper:
        return None, ''
    if upper:
        m1, b1, f1, _ = parse_meta(d)
        m2, b2, f2, _ = parse_meta(upper)
        if b1 and b1 == b2 and f1 == f2:
            return 'Cat6', '동일 층 단거리 추론'
    if p:
        try:
            p0 = int(p[0])
            p1 = int(p[1])
            if p0 > 24 or p1 > 24:
                return '광', '포트번호 추론'
        except (ValueError, TypeError):
            pass
        return 'Cat6', '포트번호 추론'
    return None, ''


# ===========================================================================
# 한 PPTX 처리
# ===========================================================================
def extract_pptx_network(pptx_path):
    """단일 PPTX 파일에서 행 데이터를 추출."""
    school = extract_school_name(pptx_path)
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(pptx_path) as z:
            z.extractall(tmp)
        slides_dir = Path(tmp) / 'ppt' / 'slides'
        if not slides_dir.exists():
            return []
        slide_files = sorted(slides_dir.glob('slide*.xml'),
                              key=lambda p: int(re.search(r'\d+', p.stem).group()))
        for slide_path in slide_files:
            slide_num = int(re.search(r'\d+', slide_path.stem).group())
            try:
                tree = ET.parse(slide_path)
            except ET.ParseError:
                continue
            text_shapes, line_shapes = walk_shapes(tree.getroot())
            devices, port_labels = extract_devices_and_ports(text_shapes)
            if not devices:
                continue
            match_ports_to_devices(devices, port_labels)
            edge_cable = extract_edges(line_shapes, devices)

            for d in devices:
                short = d['short']
                network = net_from_id(short)
                tier = tier_from_y(d['cy'])
                model, building, floor, location = parse_meta(d)
                p = d.get('port')
                port_str = f"({p[0]}→{p[1]})" if p else ''
                upper, cable = resolve_upper(d, devices, edge_cable)
                cable_pair = f"{upper['short']} → {short}" if upper else ''

                if cable:
                    uplink_cable, cable_src = cable, '추출'
                else:
                    uplink_cable, cable_src = infer_cable(d, upper, devices)
                    uplink_cable = uplink_cable or ''

                rows.append({
                    '학교명': school,
                    '슬라이드': slide_num,
                    '망': network,
                    '망ID': short,
                    '모델명': model,
                    '건물명': building,
                    '층': floor,
                    '위치': location,
                    '계위': tier,
                    '포트(다운→업)': port_str,
                    '케이블 업→다운': cable_pair,
                    '업링크 케이블': uplink_cable,
                    '케이블 출처': cable_src,
                })
    return rows
