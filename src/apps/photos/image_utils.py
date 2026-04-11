"""
사진 미디어 최적화 유틸리티

기능:
  1. resize_and_convert — max 1920px 리사이즈 + WebP 변환
  2. create_thumbnail   — 200px WebP 썸네일 생성
  3. process_photo_image — 종합 처리 (리사이즈 + 썸네일 → Photo 저장)
"""
import io
import os


def resize_and_convert(img_bytes: bytes, max_size: int = 1920) -> bytes:
    """이미지를 max_size 이하로 리사이즈하고 WebP로 변환.

    원본보다 작은 이미지는 확대하지 않음.

    Args:
        img_bytes: 원본 이미지 바이트 (JPEG/PNG/WebP 등)
        max_size:  긴 변의 최대 픽셀 수 (기본 1920)

    Returns:
        WebP 바이트
    """
    from PIL import Image

    img = Image.open(io.BytesIO(img_bytes)).convert('RGB')
    w, h = img.size

    if max(w, h) > max_size:
        if w >= h:
            new_w = max_size
            new_h = int(h * max_size / w)
        else:
            new_h = max_size
            new_w = int(w * max_size / h)
        img = img.resize((new_w, new_h), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format='WEBP', quality=85)
    return buf.getvalue()


def create_thumbnail(img_bytes: bytes, size: int = 200) -> bytes:
    """썸네일 생성 — max size × size WebP.

    Args:
        img_bytes: 원본 이미지 바이트
        size:      긴 변의 최대 픽셀 수 (기본 200)

    Returns:
        WebP 바이트
    """
    from PIL import Image

    img = Image.open(io.BytesIO(img_bytes)).convert('RGB')
    img.thumbnail((size, size), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format='WEBP', quality=80)
    return buf.getvalue()


def process_photo_image(photo, save: bool = False) -> dict:
    """Photo 인스턴스의 이미지를 최적화 처리.

    Steps:
      1. 원본 이미지 읽기
      2. 1920px 리사이즈 + WebP 변환 → image 필드 교체
      3. 200px 썸네일 생성 → thumbnail 필드 저장

    Args:
        photo: Photo 모델 인스턴스
        save:  True이면 결과를 DB에 저장

    Returns:
        {'resized': bool, 'thumbnail': bool, 'webp': bool}
    """
    from django.core.files.base import ContentFile

    result = {'resized': False, 'thumbnail': False, 'webp': False}

    try:
        with photo.image.open('rb') as f:
            original_bytes = f.read()
    except Exception:
        return result

    # ── 1. 리사이즈 + WebP 변환 ──────────────────────────────
    try:
        webp_bytes = resize_and_convert(original_bytes, max_size=1920)
        base_name = os.path.splitext(os.path.basename(photo.image.name))[0]
        webp_name = f'{base_name}.webp'

        if save:
            photo.image.save(webp_name, ContentFile(webp_bytes), save=False)

        result['resized'] = True
        result['webp'] = True
    except Exception:
        webp_bytes = original_bytes  # fallback to original

    # ── 2. 썸네일 생성 ───────────────────────────────────────
    try:
        thumb_bytes = create_thumbnail(webp_bytes, size=200)
        thumb_name = f'thumb_{base_name}.webp'

        if save:
            photo.thumbnail.save(thumb_name, ContentFile(thumb_bytes), save=False)

        result['thumbnail'] = True
    except Exception:
        pass

    if save:
        update_fields = []
        if result['webp']:
            update_fields.append('image')
        if result['thumbnail']:
            update_fields.append('thumbnail')
        if update_fields:
            photo.save(update_fields=update_fields)

    return result
