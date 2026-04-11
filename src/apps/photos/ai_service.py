"""
사진 AI 분류 실사용화 서비스

기능:
  1. check_image_quality  — PIL 기반 블러·밝기 품질 검사
  2. classify_photo_stage — 설치 전/후/기타 분류 (Claude API + 폴백)
  3. detect_defects       — 불량 설치 감지 (케이블, 레이블)
  4. analyze_photo        — 종합 AI 분석 (품질+분류+불량 통합)
  5. _call_claude_vision  — Claude Haiku vision API 호출 헬퍼
"""
import base64
import io
import json

# ──────────────────────────────────────────────────────────────
# 임계값 상수
# ──────────────────────────────────────────────────────────────
_DARK_THRESHOLD = 50      # 평균 픽셀 밝기 < 이 값 → 어두운 사진
_BLUR_THRESHOLD = 100     # Laplacian 분산 < 이 값 → 흔들린 사진
_CLAUDE_MODEL   = 'claude-haiku-4-5-20251001'


# ──────────────────────────────────────────────────────────────
# Claude Vision 헬퍼
# ──────────────────────────────────────────────────────────────
def _call_claude_vision(img_bytes: bytes, prompt: str) -> dict:
    """Claude Haiku 에 이미지+프롬프트를 보내고 JSON dict 반환.

    반환값은 프롬프트에 명시한 JSON 스키마에 따른 dict.
    네트워크 오류 등은 호출 측에서 try/except 처리.
    """
    import anthropic

    client = anthropic.Anthropic()
    b64 = base64.b64encode(img_bytes).decode()
    resp = client.messages.create(
        model=_CLAUDE_MODEL,
        max_tokens=512,
        messages=[{
            'role': 'user',
            'content': [
                {
                    'type': 'image',
                    'source': {
                        'type': 'base64',
                        'media_type': 'image/jpeg',
                        'data': b64,
                    },
                },
                {'type': 'text', 'text': prompt},
            ],
        }],
    )
    return json.loads(resp.content[0].text)


# ──────────────────────────────────────────────────────────────
# 1. 이미지 품질 검사
# ──────────────────────────────────────────────────────────────
def check_image_quality(img_bytes: bytes) -> dict:
    """PIL 기반 블러·밝기 품질 검사.

    Returns:
        {
          'quality_score': int (0~100),
          'is_blurry': bool,
          'is_dark': bool,
          'needs_retake': bool,
          'reason': str,
        }
    """
    from PIL import Image, ImageFilter
    import numpy as np

    img = Image.open(io.BytesIO(img_bytes)).convert('RGB')

    # 밝기: 그레이스케일 평균
    gray = img.convert('L')
    brightness = float(sum(gray.getdata()) / (gray.width * gray.height))
    is_dark = brightness < _DARK_THRESHOLD

    # 블러: Laplacian 분산 — 밝기가 충분히 밝은 이미지(>= 180)는 블러로 간주하지 않음
    gray_np = np.array(gray, dtype=float)
    lap = (
        gray_np[:-2, 1:-1] + gray_np[2:, 1:-1] +
        gray_np[1:-1, :-2] + gray_np[1:-1, 2:] -
        4 * gray_np[1:-1, 1:-1]
    )
    blur_var = float(lap.var())
    is_blurry = blur_var < _BLUR_THRESHOLD and brightness < 180

    # 품질 점수 (100점 기준)
    score = 100
    if is_dark:
        score -= 40
    if is_blurry:
        score -= 30
    quality_score = max(0, min(100, score))

    needs_retake = is_dark or is_blurry
    reasons = []
    if is_dark:
        reasons.append('어두운 사진')
    if is_blurry:
        reasons.append('흔들린 사진')
    reason = ', '.join(reasons)

    return {
        'quality_score': quality_score,
        'is_blurry':     is_blurry,
        'is_dark':       is_dark,
        'needs_retake':  needs_retake,
        'reason':        reason,
    }


# ──────────────────────────────────────────────────────────────
# 2. 설치 전/후 분류
# ──────────────────────────────────────────────────────────────
def classify_photo_stage(img_bytes: bytes, filename: str = '') -> dict:
    """Claude API로 설치 전/후/기타 분류.

    Claude 실패 시 파일명 키워드로 폴백.

    Returns:
        {
          'stage': 'before' | 'after' | 'other',
          'confidence': float,
          'method': 'claude' | 'fallback_filename',
        }
    """
    prompt = (
        '이 사진이 네트워크 장비 설치 작업의 전(before), 후(after), 기타(other) 중 어느 단계인지 판단하세요.\n'
        '반드시 아래 JSON 형식으로만 답하세요:\n'
        '{"stage": "before|after|other", "confidence": 0.0~1.0, "reason": "판단 근거"}'
    )
    try:
        result = _call_claude_vision(img_bytes, prompt)
        return {
            'stage':      result.get('stage', 'other'),
            'confidence': float(result.get('confidence', 0.5)),
            'method':     'claude',
        }
    except Exception:
        # 파일명 키워드 폴백
        fname_lower = filename.lower()
        if 'before' in fname_lower or '작업전' in fname_lower or '설치전' in fname_lower:
            stage = 'before'
        elif 'after' in fname_lower or '작업후' in fname_lower or '설치후' in fname_lower:
            stage = 'after'
        else:
            stage = 'other'
        return {
            'stage':      stage,
            'confidence': 0.3,
            'method':     'fallback_filename',
        }


# ──────────────────────────────────────────────────────────────
# 3. 불량 설치 감지
# ──────────────────────────────────────────────────────────────
def detect_defects(img_bytes: bytes) -> dict:
    """Claude API로 불량 설치 감지 (케이블 정리, 레이블 부착).

    Claude 실패 시 결함 없음으로 폴백.

    Returns:
        {
          'defects': {'cable_messy': bool, 'label_missing': bool, 'improper_mounting': bool},
          'defect_score': float,
          'has_defect': bool,
        }
    """
    prompt = (
        '이 네트워크 장비 설치 사진에서 불량 설치를 감지하세요.\n'
        '반드시 아래 JSON 형식으로만 답하세요:\n'
        '{"defects": {"cable_messy": true/false, "label_missing": true/false, '
        '"improper_mounting": true/false}, "defect_score": 0.0~1.0, "details": "설명"}'
    )
    _empty = {
        'defects':     {'cable_messy': False, 'label_missing': False, 'improper_mounting': False},
        'defect_score': 0.0,
        'has_defect':   False,
    }
    try:
        result = _call_claude_vision(img_bytes, prompt)
        defects = result.get('defects', {})
        defect_score = float(result.get('defect_score', 0.0))
        has_defect = any(defects.values()) if defects else False
        return {
            'defects':     defects,
            'defect_score': defect_score,
            'has_defect':   has_defect,
        }
    except Exception:
        return _empty


# ──────────────────────────────────────────────────────────────
# 4. 종합 AI 분석
# ──────────────────────────────────────────────────────────────
def analyze_photo(photo, img_bytes: bytes, save: bool = False) -> dict:
    """품질 검사 + 단계 분류 + 불량 감지 통합 실행.

    Args:
        photo: Photo 모델 인스턴스
        img_bytes: 이미지 바이트
        save: True이면 결과를 photo에 저장

    Returns:
        {
          'quality_score': float,
          'is_blurry': bool,
          'is_dark': bool,
          'needs_retake': bool,
          'retake_reason': str,
          'ai_stage': str,
          'defect_flags': dict,
          'defect_score': float,
          'has_defect': bool,
        }
    """
    quality = check_image_quality(img_bytes)

    fname = getattr(photo.image, 'name', '') or ''
    stage_result = classify_photo_stage(img_bytes, filename=fname)
    defect_result = detect_defects(img_bytes)

    result = {
        'quality_score':  quality['quality_score'],
        'is_blurry':      quality['is_blurry'],
        'is_dark':        quality['is_dark'],
        'needs_retake':   quality['needs_retake'],
        'retake_reason':  quality['reason'],
        'ai_stage':       stage_result['stage'],
        'defect_flags':   defect_result['defects'],
        'defect_score':   defect_result['defect_score'],
        'has_defect':     defect_result['has_defect'],
    }

    if save:
        photo.quality_score = result['quality_score']
        photo.is_blurry     = result['is_blurry']
        photo.is_dark       = result['is_dark']
        photo.needs_retake  = result['needs_retake']
        photo.retake_reason = result['retake_reason']
        photo.ai_stage      = result['ai_stage']
        photo.defect_flags  = result['defect_flags']
        photo.save(update_fields=[
            'quality_score', 'is_blurry', 'is_dark',
            'needs_retake', 'retake_reason', 'ai_stage', 'defect_flags',
        ])

    return result
