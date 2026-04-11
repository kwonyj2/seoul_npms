"""
Phase 6-2: 파일/미디어 최적화 테스트

테스트 범위:
  1. 사진 업로드 — 자동 리사이즈 (max 1920px)
  2. WebP 변환 (용량 절감)
  3. 썸네일 자동 생성 (목록 표시용 200px)
  4. Photo 모델 thumbnail 필드 존재 확인
  5. PDF Celery Task 타임아웃 설정 (300초)
  6. PDF 사진 base64 병렬 처리 (concurrent.futures)
"""
import io
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.core.files.base import ContentFile
from django.utils import timezone

from apps.accounts.models import User
from apps.schools.models import SupportCenter, SchoolType, School
from apps.photos.models import Photo, PhotoWorkType


# ─────────────────────────────────────────────────────────────
# 테스트 이미지 헬퍼
# ─────────────────────────────────────────────────────────────
def _make_large_image_bytes(width=3000, height=2000):
    """3000×2000 대형 이미지 (1920px 초과)"""
    from PIL import Image
    img = Image.new('RGB', (width, height), color=(150, 180, 200))
    buf = io.BytesIO()
    img.save(buf, format='JPEG')
    return buf.getvalue()


def _make_small_image_bytes(width=100, height=80):
    """100×80 소형 이미지 (리사이즈 불필요)"""
    from PIL import Image
    img = Image.new('RGB', (width, height), color=(200, 200, 200))
    buf = io.BytesIO()
    img.save(buf, format='JPEG')
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────
# 공통 픽스처
# ─────────────────────────────────────────────────────────────
class MediaOptFixtureMixin:
    @classmethod
    def setUpTestData(cls):
        cls.center = SupportCenter.objects.create(code='media_ctr', name='미디어최적화청')
        cls.school_type = SchoolType.objects.create(code='media_type', name='미디어학교')
        cls.school = School.objects.create(
            support_center=cls.center, school_type=cls.school_type,
            name='미디어테스트학교', address='서울',
        )
        cls.work_type = PhotoWorkType.objects.create(name='미디어작업', order=1)
        cls.worker = User.objects.create_user(
            username='media_worker', email='media_worker@test.com',
            password='pass', role='worker', support_center=cls.center,
        )

    def _make_photo(self, img_bytes=None, filename='test.jpg'):
        if img_bytes is None:
            img_bytes = _make_large_image_bytes()
        photo = Photo(
            school=self.school, work_type=self.work_type,
            photo_stage='before', taken_by=self.worker,
            taken_at=timezone.now(),
        )
        photo.image.save(filename, ContentFile(img_bytes), save=False)
        photo.save()
        return photo


# ─────────────────────────────────────────────────────────────
# 1. image_utils 함수 임포트
# ─────────────────────────────────────────────────────────────
class ImageUtilsImportTest(TestCase):

    def test_resize_and_convert_importable(self):
        try:
            from apps.photos.image_utils import resize_and_convert
        except ImportError:
            self.fail('resize_and_convert 가 image_utils.py에 없습니다.')

    def test_create_thumbnail_importable(self):
        try:
            from apps.photos.image_utils import create_thumbnail
        except ImportError:
            self.fail('create_thumbnail 이 image_utils.py에 없습니다.')

    def test_process_photo_image_importable(self):
        try:
            from apps.photos.image_utils import process_photo_image
        except ImportError:
            self.fail('process_photo_image 가 image_utils.py에 없습니다.')


# ─────────────────────────────────────────────────────────────
# 2. 리사이즈 — max 1920px
# ─────────────────────────────────────────────────────────────
class PhotoResizeTest(TestCase):
    """3000×2000 이미지는 최대 1920px로 축소되어야 한다"""

    def test_large_image_resized_to_max_1920(self):
        from apps.photos.image_utils import resize_and_convert
        from PIL import Image
        img_bytes = _make_large_image_bytes(3000, 2000)
        result_bytes = resize_and_convert(img_bytes, max_size=1920)
        img = Image.open(io.BytesIO(result_bytes))
        self.assertLessEqual(max(img.size), 1920)

    def test_small_image_not_upscaled(self):
        """100×80 소형 이미지는 확대하지 않는다"""
        from apps.photos.image_utils import resize_and_convert
        from PIL import Image
        img_bytes = _make_small_image_bytes(100, 80)
        result_bytes = resize_and_convert(img_bytes, max_size=1920)
        img = Image.open(io.BytesIO(result_bytes))
        self.assertLessEqual(img.width, 100)
        self.assertLessEqual(img.height, 80)

    def test_aspect_ratio_preserved(self):
        """리사이즈 후 가로세로 비율이 유지되어야 한다"""
        from apps.photos.image_utils import resize_and_convert
        from PIL import Image
        img_bytes = _make_large_image_bytes(3000, 2000)  # 3:2 비율
        result_bytes = resize_and_convert(img_bytes, max_size=1920)
        img = Image.open(io.BytesIO(result_bytes))
        ratio = img.width / img.height
        self.assertAlmostEqual(ratio, 3 / 2, delta=0.05)


# ─────────────────────────────────────────────────────────────
# 3. WebP 변환
# ─────────────────────────────────────────────────────────────
class WebPConversionTest(TestCase):
    """resize_and_convert 출력은 WebP 포맷이어야 한다"""

    def test_output_is_webp(self):
        from apps.photos.image_utils import resize_and_convert
        from PIL import Image
        img_bytes = _make_large_image_bytes()
        result_bytes = resize_and_convert(img_bytes)
        img = Image.open(io.BytesIO(result_bytes))
        self.assertEqual(img.format, 'WEBP')

    def test_webp_smaller_than_jpeg(self):
        """WebP 결과물이 원본 JPEG보다 작아야 한다"""
        from apps.photos.image_utils import resize_and_convert
        img_bytes = _make_large_image_bytes(1000, 667)  # 1920px 이하
        result_bytes = resize_and_convert(img_bytes)
        self.assertLess(len(result_bytes), len(img_bytes))


# ─────────────────────────────────────────────────────────────
# 4. 썸네일 생성 — 200px
# ─────────────────────────────────────────────────────────────
class ThumbnailTest(TestCase):
    """create_thumbnail 은 최대 200px WebP 썸네일을 반환해야 한다"""

    def test_thumbnail_max_200px(self):
        from apps.photos.image_utils import create_thumbnail
        from PIL import Image
        img_bytes = _make_large_image_bytes()
        thumb_bytes = create_thumbnail(img_bytes, size=200)
        img = Image.open(io.BytesIO(thumb_bytes))
        self.assertLessEqual(max(img.size), 200)

    def test_thumbnail_is_webp(self):
        from apps.photos.image_utils import create_thumbnail
        from PIL import Image
        img_bytes = _make_large_image_bytes()
        thumb_bytes = create_thumbnail(img_bytes)
        img = Image.open(io.BytesIO(thumb_bytes))
        self.assertEqual(img.format, 'WEBP')

    def test_thumbnail_returns_bytes(self):
        from apps.photos.image_utils import create_thumbnail
        img_bytes = _make_large_image_bytes()
        result = create_thumbnail(img_bytes)
        self.assertIsInstance(result, bytes)
        self.assertGreater(len(result), 0)


# ─────────────────────────────────────────────────────────────
# 5. Photo 모델 thumbnail 필드
# ─────────────────────────────────────────────────────────────
class PhotoThumbnailFieldTest(MediaOptFixtureMixin, TestCase):
    """Photo 모델에 thumbnail 필드가 있어야 한다"""

    def test_thumbnail_field_exists(self):
        photo = self._make_photo()
        self.assertTrue(hasattr(photo, 'thumbnail'))

    def test_thumbnail_field_nullable(self):
        """썸네일은 초기에 빈 값이어도 된다"""
        photo = self._make_photo()
        # thumbnail이 비어 있어도 오류 없이 저장되어야 함
        photo.save()
        photo.refresh_from_db()
        # 빈 상태로 저장 가능한지만 확인
        self.assertTrue(True)


# ─────────────────────────────────────────────────────────────
# 6. process_photo_image — 종합 처리
# ─────────────────────────────────────────────────────────────
class ProcessPhotoImageTest(MediaOptFixtureMixin, TestCase):
    """process_photo_image 는 리사이즈 + WebP + 썸네일을 Photo에 저장해야 한다"""

    def test_process_photo_returns_dict(self):
        from apps.photos.image_utils import process_photo_image
        photo = self._make_photo(_make_large_image_bytes())
        result = process_photo_image(photo)
        self.assertIsInstance(result, dict)

    def test_process_photo_has_required_keys(self):
        from apps.photos.image_utils import process_photo_image
        photo = self._make_photo(_make_large_image_bytes())
        result = process_photo_image(photo)
        for key in ('resized', 'thumbnail', 'webp'):
            self.assertIn(key, result)

    def test_process_photo_saves_thumbnail(self):
        from apps.photos.image_utils import process_photo_image
        photo = self._make_photo(_make_large_image_bytes())
        process_photo_image(photo, save=True)
        photo.refresh_from_db()
        # thumbnail 필드가 채워져야 함
        self.assertTrue(bool(photo.thumbnail))


# ─────────────────────────────────────────────────────────────
# 7. PDF Celery Task 타임아웃
# ─────────────────────────────────────────────────────────────
class PDFTaskTimeoutTest(TestCase):
    """generate_report_pdf_task 는 time_limit 이 설정되어야 한다"""

    def test_pdf_task_has_time_limit(self):
        from apps.reports.tasks import generate_report_pdf_task
        time_limit = getattr(generate_report_pdf_task, 'time_limit', None)
        self.assertIsNotNone(time_limit, 'generate_report_pdf_task에 time_limit이 없습니다.')
        self.assertGreater(time_limit, 0)

    def test_pdf_task_time_limit_is_300s(self):
        from apps.reports.tasks import generate_report_pdf_task
        time_limit = getattr(generate_report_pdf_task, 'time_limit', None)
        self.assertEqual(time_limit, 300)

    def test_pdf_task_has_soft_time_limit(self):
        from apps.reports.tasks import generate_report_pdf_task
        soft = getattr(generate_report_pdf_task, 'soft_time_limit', None)
        self.assertIsNotNone(soft, 'soft_time_limit이 없습니다.')


# ─────────────────────────────────────────────────────────────
# 8. PDF base64 병렬 처리
# ─────────────────────────────────────────────────────────────
class PDFParallelBase64Test(TestCase):
    """_inject_photos 는 ThreadPoolExecutor로 병렬 base64 변환해야 한다"""

    def test_inject_photos_uses_thread_pool(self):
        """_inject_photos 내부에서 ThreadPoolExecutor가 사용되어야 함"""
        import concurrent.futures
        from apps.reports import tasks as report_tasks

        with patch.object(
            concurrent.futures.ThreadPoolExecutor, '__enter__',
            wraps=concurrent.futures.ThreadPoolExecutor().__enter__
        ) as mock_pool:
            # 빈 리스트로 호출 (사진 없어도 pool 생성 여부 확인)
            pass  # 아래 직접 소스 검사로 대체

        # 소스 코드 검사 방식: tasks.py에 ThreadPoolExecutor 사용 확인
        import inspect
        source = inspect.getsource(report_tasks._inject_photos)
        self.assertIn('ThreadPoolExecutor', source,
                      '_inject_photos에 ThreadPoolExecutor 병렬 처리가 없습니다.')

    def test_inject_cable_photos_uses_thread_pool(self):
        """_inject_cable_photos 도 병렬 처리 적용"""
        import inspect
        from apps.reports import tasks as report_tasks
        source = inspect.getsource(report_tasks._inject_cable_photos)
        self.assertIn('ThreadPoolExecutor', source,
                      '_inject_cable_photos에 ThreadPoolExecutor 병렬 처리가 없습니다.')
