"""
VSDX 파서 — Visio 파일에서 건물/층/호실 정보 추출
zipfile + xml.etree.ElementTree 사용 (외부 라이브러리 불필요)
"""
import re
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Optional

NS = 'http://schemas.microsoft.com/office/visio/2012/main'

# ── 호실 분류 패턴 ────────────────────────────────────────────────────────────
_PATTERNS = {
    'class': [
        re.compile(r'\d+학년\s*\d+반'),
        re.compile(r'\d+-\d+'),
        re.compile(r'^[1-9]반$'),
        re.compile(r'학급'),
    ],
    'special': [
        re.compile(r'음악실'), re.compile(r'미술실'), re.compile(r'과학실'),
        re.compile(r'체육관'), re.compile(r'도서관?'), re.compile(r'컴퓨터실'),
        re.compile(r'어학실'), re.compile(r'영어실'), re.compile(r'기술실'),
        re.compile(r'가정실'), re.compile(r'시청각'), re.compile(r'강당'),
        re.compile(r'다목적'), re.compile(r'wee', re.I), re.compile(r'진로'),
        re.compile(r'창의'), re.compile(r'메이커'), re.compile(r'방과후'),
        re.compile(r'돌봄'), re.compile(r'유치원'), re.compile(r'전산실'),
    ],
    'office': [
        re.compile(r'교장실'), re.compile(r'교무실'), re.compile(r'행정실'),
        re.compile(r'상담실'), re.compile(r'방송실'), re.compile(r'학생실'),
        re.compile(r'보건실'), re.compile(r'숙직실'), re.compile(r'인쇄실'),
        re.compile(r'서버실'), re.compile(r'의료실'), re.compile(r'교사실'),
    ],
    'toilet': [
        re.compile(r'화장실'), re.compile(r'변소'), re.compile(r'화양실'),
        re.compile(r'^wc$', re.I),
    ],
    'support': [
        re.compile(r'계단'), re.compile(r'엘리베이터'), re.compile(r'^ev$', re.I),
        re.compile(r'복도'), re.compile(r'홀'), re.compile(r'로비'),
        re.compile(r'창고'), re.compile(r'기계실'), re.compile(r'전기실'),
        re.compile(r'통신실'), re.compile(r'소방'), re.compile(r'주차'),
        re.compile(r'현관'), re.compile(r'배관'), re.compile(r'공조'),
        re.compile(r'분전'), re.compile(r'수전'), re.compile(r'변전'),
    ],
}


def classify_room(text: str) -> str:
    for rtype, patterns in _PATTERNS.items():
        for p in patterns:
            if p.search(text):
                return rtype
    return 'support'


# ── 페이지명 → 건물명 + 층 분리 ──────────────────────────────────────────────
def parse_page_name(name: str) -> tuple[str, str, int]:
    """(건물명, 층이름, 층번호) 반환"""
    n = name.strip()

    # Visio 기본 페이지명 "페이지-N", "Page-N" → 건물명 제거 후 층 처리
    n = re.sub(r'^(페이지|Page)[\s\-_]+', '', n, flags=re.I)

    # 패턴1: "본관 1층", "본관-1층", "본관_1층", "A동 3층"
    m = re.match(r'^(.+?)[\s\-_]+(B?\d+층?|지하\s*\d+층?|\d+[Ff])$', n, re.I)
    if m:
        return m.group(1).strip(), _norm_floor(m.group(2)), _floor_num(_norm_floor(m.group(2)))

    # 패턴2: "본관1층", "별관2층" (동/관으로 끝나는 건물명 + 층)
    m = re.match(r'^(.+?[동관棟館])(B?\d+층?|\d+[Ff])$', n, re.I)
    if m:
        return m.group(1).strip(), _norm_floor(m.group(2)), _floor_num(_norm_floor(m.group(2)))

    # 패턴3: "1층(본관)", "2층(별관)"
    m = re.match(r'^(B?\d+층?)\((.+?)\)$', n)
    if m:
        fl = _norm_floor(m.group(1))
        return m.group(2).strip(), fl, _floor_num(fl)

    # 패턴4: 층만 "1층", "2층", "B1층", "지하1층", 또는 숫자만 "1", "2"
    m = re.match(r'^(B?\d+층?|지하\s*\d+층?|\d+[Ff]|\d+)$', n, re.I)
    if m:
        fl = _norm_floor(m.group(1))
        return '본관', fl, _floor_num(fl)

    # 패턴5: "1동", "2동" 처럼 숫자+동 (단독 건물명)
    m = re.match(r'^(\d+[동관])$', n)
    if m:
        return m.group(1), '1층', 1

    # 패턴6: 단독 건물명 "체육관", "급식실"
    return n, '1층', 1


def _norm_floor(raw: str) -> str:
    s = raw.strip()
    if re.match(r'^[Bb]\d+층?$', s):
        return '지하' + re.sub(r'[Bb]', '', s).replace('층', '') + '층'
    if '지하' in s:
        return s.replace(' ', '')
    if re.match(r'^\d+[Ff]$', s, re.I):
        return s[:-1] + '층'
    if re.match(r'^\d+$', s):
        return s + '층'
    return s if s.endswith('층') else s + '층'


def _floor_num(label: str) -> int:
    m = re.search(r'지하\s*(\d+)', label)
    if m:
        return -int(m.group(1))
    m = re.search(r'(\d+)', label)
    if m:
        return int(m.group(1))
    return 0


# ── 건물명 라벨 패턴 ─────────────────────────────────────────────────────────
# 형태1: "창조관", "청효관" 등 건물명 단독
_BLD_LABEL_PAT = re.compile(
    r'^[가-힣]{1,3}관$'                             # 본관, 청효관, 미래관, 명장관, 창조관
    r'|^[가-힣A-Za-z0-9]{1,4}동$'                  # A동, B동, 1동, 신축동
    r'|^제\d+동$'                                   # 제1동, 제2동
    r'|^(기숙사|별동|증축동)$'                       # 기타 독립 건물명
    r'|^[A-Za-z]{1,2}동?$',                         # GF, G, SF 등 영문 건물코드
    re.I
)
# 형태2: "청효관 1층", "미래관 2층" 등 건물명+층 라벨
_BLD_WITH_FLOOR_PAT = re.compile(
    r'^([가-힣]{1,3}[관棟館]|[가-힣A-Za-z0-9]{1,4}동)\s*(B?\d+|지하\s*\d+)\s*층?$',
    re.I
)


def _extract_building_label(text: str) -> Optional[str]:
    """건물 라벨 shape이면 건물명 반환, 아니면 None.
    '청효관 1층' → '청효관' / '창조관' → '창조관' / '체육관' → None
    """
    t = text.strip()
    # 형태2: "청효관 1층" → 건물명 "청효관" 추출
    m = _BLD_WITH_FLOOR_PAT.match(t)
    if m:
        bld_name = m.group(1)
        # 알려진 공간 유형(체육관 등)이면 건물 라벨 아님
        if all(not p.search(bld_name) for pts in _PATTERNS.values() for p in pts):
            return bld_name
        return None
    # 형태1: "창조관" 단독
    if _BLD_LABEL_PAT.match(t):
        if all(not p.search(t) for pts in _PATTERNS.values() for p in pts):
            return t
    return None


# ── 노이즈 텍스트 필터 ────────────────────────────────────────────────────────
_NOISE_EXACT = re.compile(
    r'^[xX×✕\*]{1,3}$'                          # X 표시 (공간 아님)
    r'|^\d{1,2}[FfBb]$'                          # 층수 영문 (1F, B2 등)
    r'|^\d+[:/]\d+$'                             # 축척 (1:200, 1/200)
    r'|^\d+\.?\d*\s*(mm|cm|m|M|MM|CM)$'         # 길이 단위: 11m, 5.5m, 1200mm
    r'|^\d+\.?\d*\s*[㎡㎥평]$'                   # 면적 단위: 32㎡, 15평
    r'|^\d{1,4}$'                                # 순수 숫자 (치수값: 89, 1200 등)
                                                 #   단, 5자리 이상은 우편번호 등 의미 있을 수 있어 제외
)
_NOISE_FLOOR = re.compile(
    r'^(B?\d+|지하\s*\d+)\s*층$'                          # 층 단독: "4층", "지하1층"
    r'|^[가-힣A-Za-z]{1,6}(관|동|棟|館)\s*(B?\d+|지하\s*\d+)\s*층?$'  # 건물+층: "본관5층", "A동 2층"
)
_NOISE_SCHOOL = re.compile(
    r'^[A-Z]\d{8,}'                             # NEIS 학교코드 "B107021079..."
    r'|[초중고등]+(등)?학교\s*\d*층?$'           # 학교명+층: "서울XX초등학교 4층", "고등학교"
    r'|(초등|중|고등|특수|대학교)\s*학교$'       # 학교명 단독
)

def _is_noise(text: str) -> bool:
    """도면 라벨·기호 등 공간이 아닌 텍스트 판별"""
    t = text.strip()
    if _NOISE_EXACT.match(t):
        return True
    if _NOISE_FLOOR.match(t):
        return True
    if _NOISE_SCHOOL.search(t):
        return True
    return False


# ── Shape 텍스트/좌표 추출 ────────────────────────────────────────────────────
def _get_text(shape: ET.Element) -> str:
    texts = []
    for child in shape:
        tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
        if tag == 'Text':
            buf = ''
            for node in child.iter():
                nt = node.tag.split('}')[-1] if '}' in node.tag else node.tag
                if nt in ('pp', 'cp', 'Text'):
                    # tail text (텍스트 런 사이 내용)은 수집
                    if node.tail:
                        buf += node.tail
                    continue
                if node.text:
                    buf += node.text
                if node.tail:
                    buf += node.tail
            clean = re.sub(r'\s+', ' ', buf).strip()
            if clean:
                texts.append(clean)
    return ' '.join(texts).strip()


def _get_cell(shape: ET.Element, name: str) -> Optional[float]:
    def _parse(v):
        if v is not None and v != '':
            try:
                return float(v)
            except ValueError:
                pass
        return None

    for child in shape:
        tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
        # 패턴 1: Shape > Cell (직접, 가장 흔한 구조)
        if tag == 'Cell' and child.get('N') == name:
            r = _parse(child.get('V'))
            if r is not None:
                return r
        # 패턴 2: Shape > Cells > Cell
        if tag == 'Cells':
            for cell in child:
                ctag = cell.tag.split('}')[-1] if '}' in cell.tag else cell.tag
                if ctag == 'Cell' and cell.get('N') == name:
                    r = _parse(cell.get('V'))
                    if r is not None:
                        return r
    # 패턴 3: Shape > Section > Row > Cell (Visio 2016+)
    for sec in shape:
        stag = sec.tag.split('}')[-1] if '}' in sec.tag else sec.tag
        if stag != 'Section':
            continue
        for row in sec:
            for cell in row:
                ctag = cell.tag.split('}')[-1] if '}' in cell.tag else cell.tag
                if ctag == 'Cell' and cell.get('N') == name:
                    r = _parse(cell.get('V'))
                    if r is not None:
                        return r
    return None


# ── 호실번호 부여 ─────────────────────────────────────────────────────────────
def assign_room_numbers(rooms: list[dict], floor_num: int) -> list[dict]:
    """층번호 기반 일련번호: 1층→101,102... 2층→201,202... 지하1층→B101...
    모든 공간에 번호 부여 — 교실명은 매년 바뀌므로 호실번호로 위치 식별"""
    prefix = f'B{abs(floor_num)}' if floor_num < 0 else str(abs(floor_num))
    # 호실 수에 따라 자릿수 결정: ≤99개→2자리(101), 100~999개→3자리(1001)
    pad = max(2, len(str(len(rooms))))
    counter = 1
    for r in rooms:
        r['room_number'] = f'{prefix}{counter:0{pad}d}'
        counter += 1
    return rooms


# ── 메인 파서 ─────────────────────────────────────────────────────────────────
@dataclass
class RoomData:
    name: str
    room_type: str
    room_number: str = ''
    area_m2: Optional[float] = None
    pos_x: Optional[float] = None
    pos_y: Optional[float] = None
    pos_w: Optional[float] = None
    pos_h: Optional[float] = None


@dataclass
class FloorData:
    floor_name: str
    floor_num: int
    rooms: list[RoomData] = field(default_factory=list)


@dataclass
class BuildingData:
    name: str
    floors: list[FloorData] = field(default_factory=list)


@dataclass
class ParseResult:
    school_name: str
    buildings: list[BuildingData] = field(default_factory=list)
    total_rooms: int = 0
    error: str = ''


def parse_vsdx(file_path: str) -> ParseResult:
    """VSDX 파일을 파싱하여 건물/층/호실 데이터 반환"""
    import os
    school_name = os.path.splitext(os.path.basename(file_path))[0]
    result = ParseResult(school_name=school_name)

    try:
        with zipfile.ZipFile(file_path, 'r') as zf:
            names = zf.namelist()

            # pages.xml 파싱
            if 'visio/pages/pages.xml' not in names:
                result.error = 'pages.xml 없음 — VSDX 구조 이상'
                return result

            pages_xml = zf.read('visio/pages/pages.xml').decode('utf-8', errors='replace')
            pages_root = ET.fromstring(pages_xml)
            page_els = pages_root.findall(f'.//{{{NS}}}Page')

            bld_map: dict[str, BuildingData] = {}

            for i, page_el in enumerate(page_els, start=1):
                page_name = page_el.get('Name') or page_el.get('NameU') or str(i)
                page_key = f'visio/pages/page{i}.xml'
                if page_key not in names:
                    continue

                page_xml = zf.read(page_key).decode('utf-8', errors='replace')
                page_root = ET.fromstring(page_xml)
                shapes = page_root.findall(f'.//{{{NS}}}Shape')

                bld_name, floor_label, floor_num = parse_page_name(page_name)

                # ── Shape 수집 (건물 라벨 / 호실 분리) ───────────────────────
                bld_anchors: list[tuple[str, float, float]] = []  # (건물명, x, y)
                rooms: list[RoomData] = []

                for sh in shapes:
                    text = _get_text(sh)
                    if not text or len(text) < 2:
                        continue
                    px = _get_cell(sh, 'PinX')
                    py = _get_cell(sh, 'PinY')
                    w  = _get_cell(sh, 'Width')
                    h  = _get_cell(sh, 'Height')
                    if px is None and py is None:
                        continue

                    # 건물명 라벨 먼저 확인 (노이즈 체크 전: "청효관 1층" 등이 noise로 걸릴 수 있음)
                    bld_label = _extract_building_label(text)
                    if bld_label:
                        bld_anchors.append((bld_label, px or 0, py or 0))
                        continue

                    if _is_noise(text):
                        continue

                    # 면적: inch² → ㎡ (1inch = 0.0254m)
                    area = round((w or 0) * (h or 0) * 0.0929, 2) if w and h else None

                    rooms.append(RoomData(
                        name=text,
                        room_type=classify_room(text),
                        area_m2=area if area and area > 0 else None,
                        pos_x=round(px, 4) if px is not None else None,
                        pos_y=round(py, 4) if py is not None else None,
                        pos_w=round(w, 4) if w is not None else None,
                        pos_h=round(h, 4) if h is not None else None,
                    ))

                if not rooms:
                    continue

                # ── 건물 라벨이 2개 이상: 근접도 기반 건물 분리 ──────────────
                if len(bld_anchors) >= 2:
                    grouped: dict[str, list[RoomData]] = {a[0]: [] for a in bld_anchors}
                    for room in rooms:
                        rx, ry = room.pos_x or 0, room.pos_y or 0
                        nearest = min(bld_anchors,
                                      key=lambda a: (a[1] - rx) ** 2 + (a[2] - ry) ** 2)
                        grouped[nearest[0]].append(room)

                    for grp_bld, grp_rooms in grouped.items():
                        if not grp_rooms:
                            continue
                        grp_rooms.sort(key=lambda r: (-(r.pos_y or 0), (r.pos_x or 0)))
                        rd = [vars(r) for r in grp_rooms]
                        assign_room_numbers(rd, floor_num)
                        grp_rooms = [RoomData(**d) for d in rd]

                        if grp_bld not in bld_map:
                            bld_map[grp_bld] = BuildingData(name=grp_bld)
                        existing = next((f for f in bld_map[grp_bld].floors
                                         if f.floor_num == floor_num), None)
                        if existing:
                            existing.rooms.extend(grp_rooms)
                        else:
                            bld_map[grp_bld].floors.append(
                                FloorData(floor_name=floor_label,
                                          floor_num=floor_num, rooms=grp_rooms)
                            )
                    continue  # 다음 페이지로

                # ── 건물 라벨 없음(기본): 페이지명 건물로 전체 귀속 ───────────
                rooms.sort(key=lambda r: (-(r.pos_y or 0), (r.pos_x or 0)))
                rooms_dict = [vars(r) for r in rooms]
                assign_room_numbers(rooms_dict, floor_num)
                rooms = [RoomData(**d) for d in rooms_dict]

                if bld_name not in bld_map:
                    bld_map[bld_name] = BuildingData(name=bld_name)

                # 같은 건물·층 데이터가 이미 있으면 합치기
                existing = next((f for f in bld_map[bld_name].floors
                                 if f.floor_num == floor_num), None)
                if existing:
                    existing.rooms.extend(rooms)
                else:
                    bld_map[bld_name].floors.append(
                        FloorData(floor_name=floor_label, floor_num=floor_num, rooms=rooms)
                    )

            for bld in bld_map.values():
                bld.floors.sort(key=lambda f: -f.floor_num)
                result.buildings.append(bld)

            result.total_rooms = sum(
                len(f.rooms)
                for b in result.buildings
                for f in b.floors
            )

    except zipfile.BadZipFile:
        result.error = '유효하지 않은 VSDX(ZIP) 파일'
    except ET.ParseError as e:
        result.error = f'XML 파싱 오류: {e}'
    except Exception as e:
        result.error = f'파싱 실패: {e}'

    return result
