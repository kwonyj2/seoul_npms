"""
AI 분류 라우터
- 이미지 자동 분류 (작업 유형 추정)
- 문서 자동 분류 (NAS 카테고리 추정)
"""
import io
import logging
from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()


# ── 이미지 분류 ─────────────────────────────────────────────────────────────
# 경량 키워드 기반 분류 (EXIF, 파일명, 색상 히스토그램 활용)
# 무거운 YOLOv8 대신 간단한 휴리스틱 + 색상 특징 사용
IMAGE_CATEGORIES = [
    'switch_install',   # 스위치 설치
    'cable_work',       # 케이블 공사
    'rack_install',     # 랙 설치
    'incident',         # 장애처리
    'regular_check',    # 정기점검
    'before_work',      # 작업전
    'after_work',       # 작업후
    'other',            # 기타
]

IMAGE_LABEL_KO = {
    'switch_install': '스위치설치',
    'cable_work':     '케이블공사',
    'rack_install':   '랙설치',
    'incident':       '장애처리',
    'regular_check':  '정기점검',
    'before_work':    '작업전',
    'after_work':     '작업후',
    'other':          '기타',
}


class ClassifyResult(BaseModel):
    category:    str
    category_ko: str
    confidence:  float
    method:      str


@router.post("/image/", response_model=ClassifyResult)
async def classify_image(file: UploadFile = File(...)):
    """
    이미지 파일 자동 분류
    - 파일명 키워드 분석
    - 색상 히스토그램 (파란색 = 스위치, 회색 = 랙, 녹색 = 케이블)
    """
    filename = (file.filename or '').lower()
    data = await file.read()

    # 1. 파일명 기반 키워드 분류
    category, confidence = _classify_by_filename(filename)
    method = 'filename_keyword'

    # 2. 파일명 단서가 없으면 색상 히스토그램 분류
    if confidence < 0.5:
        try:
            cat2, conf2 = _classify_by_color(data)
            if conf2 > confidence:
                category, confidence = cat2, conf2
                method = 'color_histogram'
        except Exception as e:
            logger.debug(f'Color classify failed: {e}')

    return ClassifyResult(
        category=category,
        category_ko=IMAGE_LABEL_KO.get(category, '기타'),
        confidence=round(confidence, 3),
        method=method,
    )


def _classify_by_filename(filename: str):
    """파일명 키워드 → 카테고리"""
    rules = [
        (['switch', '스위치', 'sw_'],        'switch_install', 0.85),
        (['cable', '케이블', 'utp', 'patch'], 'cable_work',     0.85),
        (['rack', '랙'],                      'rack_install',   0.80),
        (['before', '작업전', '_b_'],         'before_work',    0.80),
        (['after',  '작업후', '_a_'],         'after_work',     0.80),
        (['check', '점검', 'inspect'],        'regular_check',  0.75),
        (['fault', '장애', 'incident'],       'incident',       0.75),
    ]
    for keywords, cat, conf in rules:
        if any(kw in filename for kw in keywords):
            return cat, conf
    return 'other', 0.3


def _classify_by_color(data: bytes):
    """PIL 색상 히스토그램 분석"""
    from PIL import Image
    import numpy as np
    img = Image.open(io.BytesIO(data)).convert('RGB').resize((64, 64))
    arr = np.array(img, dtype=float)

    r_mean = arr[:, :, 0].mean()
    g_mean = arr[:, :, 1].mean()
    b_mean = arr[:, :, 2].mean()

    # 파란색 계열 → 스위치 (네트워크 장비 주로 파란색 LED)
    if b_mean > r_mean + 20 and b_mean > g_mean + 10:
        return 'switch_install', 0.60
    # 회색 계열 → 랙 (금속 랙)
    if abs(r_mean - g_mean) < 10 and abs(g_mean - b_mean) < 10 and r_mean < 150:
        return 'rack_install', 0.55
    # 녹색 계열 → 케이블
    if g_mean > r_mean + 15 and g_mean > b_mean + 15:
        return 'cable_work', 0.55

    return 'other', 0.35


# ── 문서 분류 ─────────────────────────────────────────────────────────────

DOC_CATEGORIES = {
    'report':   ['산출물', '완료보고', '결과보고', '사업결과'],
    'incident': ['장애', '장애처리', '장애보고', 'trouble'],
    'regular':  ['정기점검', '점검표', '월별점검', '분기점검'],
    'cable':    ['케이블', '랜공사', 'utp', '배선'],
    'switch':   ['스위치', 'c3100', 'c2960', '스위치설치', '스위치교체'],
    'photo':    ['사진', '작업사진', '현장사진'],
    'other':    [],
}


class DocClassifyRequest(BaseModel):
    filename: str = ''
    text:     str = ''


class DocClassifyResult(BaseModel):
    category:   str
    confidence: float
    matched:    list


@router.post("/document/", response_model=DocClassifyResult)
async def classify_document(req: DocClassifyRequest):
    """
    NAS 문서 자동 분류
    - 파일명 + OCR 텍스트 키워드 분석
    """
    combined = (req.filename + ' ' + req.text).lower()
    scores = {}
    matched_words = {}

    for cat, keywords in DOC_CATEGORIES.items():
        hits = [kw for kw in keywords if kw in combined]
        scores[cat]  = len(hits)
        matched_words[cat] = hits

    best_cat = max(scores, key=scores.get)
    best_score = scores[best_cat]

    if best_score == 0:
        return DocClassifyResult(category='other', confidence=0.3, matched=[])

    total = sum(scores.values())
    confidence = round(best_score / total, 2) if total > 0 else 0.3

    return DocClassifyResult(
        category=best_cat,
        confidence=min(confidence + 0.3, 0.95),
        matched=matched_words[best_cat],
    )
