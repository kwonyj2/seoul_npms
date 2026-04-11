"""
Phase 7-1: 입력 검증 강화 테스트

테스트 범위:
  1. MIME type 서버사이드 검증 (python-magic / filetype)
  2. PIL 실제 이미지 여부 검증
  3. 최대 파일 크기 제한
  4. 파일명 sanitize (path traversal 방지)
  5. PhotoUploadSerializer 검증 강화
  6. 원시 SQL 점검 (read-only 확인)
"""
import io
from unittest.mock import MagicMock
from django.test import TestCase, override_settings
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.schools.models import SupportCenter, SchoolType, School
from apps.photos.models import PhotoWorkType


# ─────────────────────────────────────────────────────────────
# 테스트 파일 생성 헬퍼
# ─────────────────────────────────────────────────────────────
def _make_image_file(width=100, height=100, fmt='JPEG', name='test.jpg'):
    from PIL import Image
    img = Image.new('RGB', (width, height), color=(100, 150, 200))
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    buf.seek(0)
    return InMemoryUploadedFile(
        buf, 'image', name, f'image/{fmt.lower()}', buf.getbuffer().nbytes, None
    )


def _make_text_file(content=b'not an image', name='fake.jpg'):
    buf = io.BytesIO(content)
    return InMemoryUploadedFile(
        buf, 'image', name, 'image/jpeg', len(content), None
    )


def _make_large_image_file(size_mb=25):
    """MAX_UPLOAD_SIZE 초과 파일"""
    buf = io.BytesIO(b'X' * (size_mb * 1024 * 1024))
    return InMemoryUploadedFile(
        buf, 'image', 'large.jpg', 'image/jpeg', buf.getbuffer().nbytes, None
    )


# ─────────────────────────────────────────────────────────────
# 1. 검증기 임포트 확인
# ─────────────────────────────────────────────────────────────
class ValidatorsImportTest(TestCase):

    def test_validate_image_importable(self):
        try:
            from core.validators import validate_image_file
        except ImportError:
            self.fail('core.validators.validate_image_file 가 없습니다.')

    def test_sanitize_filename_importable(self):
        try:
            from core.validators import sanitize_filename
        except ImportError:
            self.fail('core.validators.sanitize_filename 이 없습니다.')

    def test_max_upload_size_setting(self):
        """settings.MAX_UPLOAD_SIZE 가 정의되어야 한다"""
        from django.conf import settings
        self.assertTrue(
            hasattr(settings, 'MAX_UPLOAD_SIZE'),
            'MAX_UPLOAD_SIZE 설정이 없습니다.'
        )
        self.assertGreater(settings.MAX_UPLOAD_SIZE, 0)

    def test_max_upload_size_is_reasonable(self):
        """MAX_UPLOAD_SIZE 는 1MB ~ 50MB 사이여야 한다"""
        from django.conf import settings
        size_mb = settings.MAX_UPLOAD_SIZE / (1024 * 1024)
        self.assertGreaterEqual(size_mb, 1)
        self.assertLessEqual(size_mb, 50)


# ─────────────────────────────────────────────────────────────
# 2. MIME type / PIL 이미지 검증
# ─────────────────────────────────────────────────────────────
class ImageValidationTest(TestCase):
    """validate_image_file 핵심 동작"""

    def test_valid_jpeg_passes(self):
        """유효한 JPEG 이미지는 통과해야 한다"""
        from core.validators import validate_image_file
        from django.core.exceptions import ValidationError
        f = _make_image_file(name='photo.jpg')
        try:
            validate_image_file(f)  # 예외 없어야 함
        except ValidationError:
            self.fail('유효한 JPEG가 거부되었습니다.')

    def test_valid_png_passes(self):
        """유효한 PNG 이미지는 통과해야 한다"""
        from core.validators import validate_image_file
        from django.core.exceptions import ValidationError
        f = _make_image_file(fmt='PNG', name='photo.png')
        try:
            validate_image_file(f)
        except ValidationError:
            self.fail('유효한 PNG가 거부되었습니다.')

    def test_text_file_with_jpg_extension_rejected(self):
        """JPEG 확장자지만 텍스트 파일은 거부되어야 한다"""
        from core.validators import validate_image_file
        from django.core.exceptions import ValidationError
        f = _make_text_file(b'This is not an image', name='fake.jpg')
        with self.assertRaises(ValidationError):
            validate_image_file(f)

    def test_executable_disguised_as_image_rejected(self):
        """실행 파일을 이미지로 위장한 경우 거부"""
        from core.validators import validate_image_file
        from django.core.exceptions import ValidationError
        # ELF 바이너리 헤더
        f = _make_text_file(b'\x7fELF\x02\x01\x01', name='evil.jpg')
        with self.assertRaises(ValidationError):
            validate_image_file(f)

    def test_html_disguised_as_image_rejected(self):
        """HTML 파일을 이미지로 위장한 경우 거부"""
        from core.validators import validate_image_file
        from django.core.exceptions import ValidationError
        f = _make_text_file(b'<script>alert(1)</script>', name='xss.jpg')
        with self.assertRaises(ValidationError):
            validate_image_file(f)


# ─────────────────────────────────────────────────────────────
# 3. 파일 크기 제한
# ─────────────────────────────────────────────────────────────
class FileSizeLimitTest(TestCase):
    """MAX_UPLOAD_SIZE 초과 시 거부"""

    def test_oversized_file_rejected(self):
        """MAX_UPLOAD_SIZE 초과 파일은 ValidationError"""
        from core.validators import validate_image_file
        from django.core.exceptions import ValidationError
        from django.conf import settings
        # MAX_UPLOAD_SIZE + 1 바이트 파일
        buf = io.BytesIO(b'X' * (settings.MAX_UPLOAD_SIZE + 1))
        f = InMemoryUploadedFile(
            buf, 'image', 'big.jpg', 'image/jpeg', buf.getbuffer().nbytes, None
        )
        with self.assertRaises(ValidationError):
            validate_image_file(f)

    def test_normal_size_file_passes(self):
        """정상 크기 이미지는 통과"""
        from core.validators import validate_image_file
        from django.core.exceptions import ValidationError
        f = _make_image_file()
        try:
            validate_image_file(f)
        except ValidationError:
            self.fail('정상 크기 이미지가 거부되었습니다.')


# ─────────────────────────────────────────────────────────────
# 4. 파일명 sanitize
# ─────────────────────────────────────────────────────────────
class FilenameSecurityTest(TestCase):
    """sanitize_filename path traversal / 특수문자 방어"""

    def test_path_traversal_removed(self):
        """../etc/passwd 는 안전한 이름으로 변환"""
        from core.validators import sanitize_filename
        result = sanitize_filename('../etc/passwd')
        self.assertNotIn('..', result)
        self.assertNotIn('/', result)

    def test_absolute_path_removed(self):
        """/etc/passwd → 경로 없이 파일명만"""
        from core.validators import sanitize_filename
        result = sanitize_filename('/etc/passwd')
        self.assertNotIn('/', result)

    def test_null_bytes_removed(self):
        """null byte injection 방어"""
        from core.validators import sanitize_filename
        result = sanitize_filename('evil\x00.jpg')
        self.assertNotIn('\x00', result)

    def test_normal_filename_preserved(self):
        """일반 파일명은 그대로 유지 (또는 유사하게)"""
        from core.validators import sanitize_filename
        result = sanitize_filename('photo_2026.jpg')
        self.assertIn('.jpg', result)
        # 파일명의 핵심은 유지되어야 함

    def test_windows_path_separator_removed(self):
        """Windows 경로 구분자 제거"""
        from core.validators import sanitize_filename
        result = sanitize_filename('C:\\Users\\evil\\photo.jpg')
        self.assertNotIn('\\', result)
        self.assertNotIn(':', result)


# ─────────────────────────────────────────────────────────────
# 5. PhotoUploadSerializer 검증 강화
# ─────────────────────────────────────────────────────────────
class PhotoSerializerValidationTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.center = SupportCenter.objects.create(code='val_ctr', name='검증테스트청')
        cls.school_type = SchoolType.objects.create(code='val_type', name='검증테스트학교')
        cls.school = School.objects.create(
            support_center=cls.center, school_type=cls.school_type,
            name='검증테스트학교', address='서울',
        )
        cls.work_type = PhotoWorkType.objects.create(name='검증작업', order=1)
        cls.worker = User.objects.create_user(
            username='val_worker', email='val_worker@test.com',
            password='pass', role='worker', support_center=cls.center,
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.worker)

    def test_valid_image_accepted(self):
        """유효한 이미지 업로드는 201 반환"""
        img_file = _make_image_file()
        data = {
            'school': self.school.pk,
            'work_type': self.work_type.pk,
            'photo_stage': 'before',
            'image': img_file,
            'taken_at': timezone.now().isoformat(),
        }
        resp = self.client.post('/api/photos/photos/', data, format='multipart')
        # 201 (created) 또는 200
        self.assertIn(resp.status_code, [200, 201])

    def test_non_image_file_rejected(self):
        """텍스트 파일을 이미지로 위장하면 400 거부"""
        fake = _make_text_file(b'not an image', name='evil.jpg')
        data = {
            'school': self.school.pk,
            'work_type': self.work_type.pk,
            'photo_stage': 'before',
            'image': fake,
            'taken_at': timezone.now().isoformat(),
        }
        resp = self.client.post('/api/photos/photos/', data, format='multipart')
        self.assertEqual(resp.status_code, 400)

    def test_oversized_image_rejected(self):
        """MAX_UPLOAD_SIZE 초과 이미지는 400"""
        from django.conf import settings
        buf = io.BytesIO(b'X' * (settings.MAX_UPLOAD_SIZE + 1))
        f = InMemoryUploadedFile(
            buf, 'image', 'big.jpg', 'image/jpeg', buf.getbuffer().nbytes, None
        )
        data = {
            'school': self.school.pk,
            'work_type': self.work_type.pk,
            'photo_stage': 'before',
            'image': f,
            'taken_at': timezone.now().isoformat(),
        }
        resp = self.client.post('/api/photos/photos/', data, format='multipart')
        self.assertEqual(resp.status_code, 400)


# ─────────────────────────────────────────────────────────────
# 6. raw SQL 안전성 확인
# ─────────────────────────────────────────────────────────────
class RawSQLSafetyTest(TestCase):
    """apps/sysconfig/api.py의 raw SQL이 read-only인지 확인"""

    def test_sysconfig_raw_sql_is_read_only(self):
        """sysconfig raw SQL은 SELECT만 사용해야 한다"""
        import inspect
        import apps.sysconfig.api as sysconfig_api
        source = inspect.getsource(sysconfig_api)
        # execute 호출 라인에서 SELECT만 사용
        lines = source.split('\n')
        for line in lines:
            if 'execute(' in line and 'SELECT' not in line and '#' not in line:
                # 위험한 raw SQL 패턴: execute() but no SELECT
                self.fail(f'위험한 raw SQL 발견: {line.strip()}')
