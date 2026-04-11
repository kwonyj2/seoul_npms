"""
입력 검증 강화 유틸리티

기능:
  1. validate_image_file — MIME type + PIL 실제 이미지 여부 + 파일 크기 검증
  2. sanitize_filename   — path traversal / 특수문자 방어
"""
import os
import re
import io
import logging

from django.core.exceptions import ValidationError
from django.conf import settings

logger = logging.getLogger(__name__)

# ── 허용 이미지 확장자 / MIME ──────────────────────────────────
_ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
_ALLOWED_PIL_FORMATS = {'JPEG', 'PNG', 'GIF', 'WEBP'}

# ── 파일명 안전 문자 패턴 ──────────────────────────────────────
_UNSAFE_CHARS = re.compile(r'[^\w\s.\-]', re.UNICODE)
_MAX_FILENAME_LEN = 255


def validate_image_file(file):
    """업로드 파일이 실제 이미지인지 다단계 검증.

    검증 순서:
      1. 파일 크기 (MAX_UPLOAD_SIZE)
      2. 파일 확장자
      3. PIL Image.open() 으로 실제 이미지 여부 확인

    Args:
        file: Django UploadedFile 또는 InMemoryUploadedFile

    Raises:
        ValidationError: 검증 실패 시
    """
    max_size = getattr(settings, 'MAX_UPLOAD_SIZE', 20 * 1024 * 1024)

    # ── 1. 파일 크기 ──────────────────────────────────────────
    if file.size > max_size:
        limit_mb = max_size / (1024 * 1024)
        raise ValidationError(
            f'파일 크기가 제한({limit_mb:.0f}MB)을 초과합니다. '
            f'현재 크기: {file.size / (1024 * 1024):.1f}MB'
        )

    # ── 2. 확장자 검사 ────────────────────────────────────────
    name = getattr(file, 'name', '') or ''
    ext = os.path.splitext(name)[1].lower()
    if ext and ext not in _ALLOWED_EXTENSIONS:
        raise ValidationError(
            f'허용되지 않는 파일 형식입니다. 허용: {", ".join(_ALLOWED_EXTENSIONS)}'
        )

    # ── 3. PIL 실제 이미지 검증 ───────────────────────────────
    file.seek(0)
    raw = file.read(10 * 1024 * 1024)  # 최대 10MB 읽기
    file.seek(0)

    try:
        from PIL import Image, UnidentifiedImageError
        img = Image.open(io.BytesIO(raw))
        img.verify()  # 파일 손상 여부 확인
        fmt = img.format
        if fmt not in _ALLOWED_PIL_FORMATS:
            raise ValidationError(
                f'허용되지 않는 이미지 포맷입니다: {fmt}'
            )
    except ValidationError:
        raise
    except Exception as e:
        raise ValidationError(
            f'유효하지 않은 이미지 파일입니다: {e}'
        )


class PasswordComplexityValidator:
    """비밀번호 복잡도 검증: 대문자·숫자·특수문자 각 1자 이상"""

    SPECIAL = r'[!@#$%^&*()_+\-=\[\]{};\'\"\\|,.<>/?`~]'

    def validate(self, password, user=None):
        errors = []
        if not re.search(r'[A-Z]', password):
            errors.append('대문자를 1자 이상 포함해야 합니다.')
        if not re.search(r'\d', password):
            errors.append('숫자를 1자 이상 포함해야 합니다.')
        if not re.search(self.SPECIAL, password):
            errors.append('특수문자를 1자 이상 포함해야 합니다.')
        if errors:
            raise ValidationError(errors)

    def get_help_text(self):
        return '대문자, 숫자, 특수문자를 각 1자 이상 포함해야 합니다.'


def sanitize_filename(filename: str) -> str:
    """파일명에서 보안 위협 요소 제거.

    - path traversal (../, /, \\) 제거
    - null byte 제거
    - 위험 특수문자 제거
    - 길이 제한

    Args:
        filename: 원본 파일명 (경로 포함 가능)

    Returns:
        안전한 파일명 문자열
    """
    if not filename:
        return 'upload'

    # null byte 제거
    filename = filename.replace('\x00', '')

    # 경로 구분자 처리 → 파일명만 추출
    filename = filename.replace('\\', '/').replace(':', '_')
    # basename만 취함 (path traversal 방지)
    filename = os.path.basename(filename)

    # 추가 .. 제거
    filename = filename.replace('..', '')

    # 안전하지 않은 문자 제거 (알파벳, 숫자, 공백, ., -, _ 외 제거)
    name, ext = os.path.splitext(filename)
    name = _UNSAFE_CHARS.sub('_', name)
    ext = _UNSAFE_CHARS.sub('', ext)

    # 길이 제한
    safe = (name + ext)[:_MAX_FILENAME_LEN] or 'upload'
    return safe
