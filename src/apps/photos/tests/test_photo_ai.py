"""
Phase 5-3: 사진 AI 분류 실사용화 테스트

테스트 범위:
  1. Photo 모델 — 품질/불량/재촬영 신규 필드 존재 확인
  2. check_image_quality() — PIL 기반 블러·밝기 품질 검사
  3. classify_photo_stage() — 설치 전/후/기타 분류 (Claude API or 폴백)
  4. detect_defects() — 불량 설치 감지 (케이블 정리, 레이블)
  5. analyze_photo() — 종합 AI 분석 (품질+분류+불량 통합)
  6. 사진 품질 미달 시 needs_retake=True 자동 설정
  7. POST /api/photos/{id}/analyze/ — AI 분석 트리거 API
  8. GET /api/photos/quality-issues/ — 재촬영 필요 사진 목록 API
  9. Claude API 장애 시 폴백 동작 확인
 10. ai_server classify endpoint 확장 테스트
"""
import io
import json
from unittest.mock import patch, MagicMock
from datetime import datetime

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.schools.models import SupportCenter, SchoolType, School
from apps.photos.models import Photo, PhotoWorkType


# ─────────────────────────────────────────────────────────────
# 테스트용 이미지 생성 헬퍼
# ─────────────────────────────────────────────────────────────
def _make_bright_image_bytes(width=100, height=100, brightness=200):
    """밝은 선명한 이미지 바이트"""
    from PIL import Image
    img = Image.new('RGB', (width, height), color=(brightness, brightness, brightness))
    buf = io.BytesIO()
    img.save(buf, format='JPEG')
    return buf.getvalue()


def _make_dark_image_bytes(width=100, height=100):
    """어두운 이미지 바이트"""
    from PIL import Image
    img = Image.new('RGB', (width, height), color=(20, 20, 20))
    buf = io.BytesIO()
    img.save(buf, format='JPEG')
    return buf.getvalue()


def _make_blurry_image_bytes(width=100, height=100):
    """단색 (에지 없음 = 블러 유사) 이미지 바이트"""
    from PIL import Image
    img = Image.new('RGB', (width, height), color=(128, 128, 128))
    buf = io.BytesIO()
    img.save(buf, format='JPEG')
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────
# 공통 픽스처
# ─────────────────────────────────────────────────────────────
class PhotoAIFixtureMixin:
    @classmethod
    def setUpTestData(cls):
        cls.center = SupportCenter.objects.create(
            code='photo_center', name='사진테스트청',
        )
        cls.school_type = SchoolType.objects.create(
            code='photo_type', name='사진테스트학교'
        )
        cls.school = School.objects.create(
            support_center=cls.center, school_type=cls.school_type,
            name='사진테스트학교', address='서울',
        )
        cls.work_type = PhotoWorkType.objects.create(name='스위치설치', order=1)
        cls.worker = User.objects.create_user(
            username='photo_worker', email='photo_worker@test.com',
            password='pass', role='worker',
            support_center=cls.center,
        )

    def _make_photo(self, stage='before', filename='test_photo.jpg'):
        from django.core.files.base import ContentFile
        img_bytes = _make_bright_image_bytes()
        photo = Photo(
            school=self.school,
            work_type=self.work_type,
            photo_stage=stage,
            taken_by=self.worker,
            taken_at=timezone.now(),
        )
        photo.image.save(filename, ContentFile(img_bytes), save=False)
        photo.save()
        return photo


# ─────────────────────────────────────────────────────────────
# 1. Photo 모델 신규 필드 존재 확인
# ─────────────────────────────────────────────────────────────
class PhotoModelNewFieldsTest(PhotoAIFixtureMixin, TestCase):
    """Photo 모델에 품질·불량·재촬영 필드가 추가되어야 한다"""

    def test_quality_score_field_exists(self):
        photo = self._make_photo()
        self.assertTrue(hasattr(photo, 'quality_score'))

    def test_is_blurry_field_exists(self):
        photo = self._make_photo()
        self.assertTrue(hasattr(photo, 'is_blurry'))

    def test_is_dark_field_exists(self):
        photo = self._make_photo()
        self.assertTrue(hasattr(photo, 'is_dark'))

    def test_defect_flags_field_exists(self):
        photo = self._make_photo()
        self.assertTrue(hasattr(photo, 'defect_flags'))
        self.assertIsInstance(photo.defect_flags, dict)

    def test_needs_retake_field_exists(self):
        photo = self._make_photo()
        self.assertTrue(hasattr(photo, 'needs_retake'))
        self.assertFalse(photo.needs_retake)

    def test_retake_reason_field_exists(self):
        photo = self._make_photo()
        self.assertTrue(hasattr(photo, 'retake_reason'))

    def test_ai_stage_field_exists(self):
        """AI가 판단한 before/after/other 필드"""
        photo = self._make_photo()
        self.assertTrue(hasattr(photo, 'ai_stage'))


# ─────────────────────────────────────────────────────────────
# 2. check_image_quality() — 품질 검사
# ─────────────────────────────────────────────────────────────
class ImageQualityCheckTest(TestCase):
    """PIL 기반 이미지 품질 검사"""

    def test_function_importable(self):
        try:
            from apps.photos.ai_service import check_image_quality
        except ImportError:
            self.fail('check_image_quality 가 ai_service.py에 없습니다.')

    def test_bright_image_is_good_quality(self):
        from apps.photos.ai_service import check_image_quality
        img_bytes = _make_bright_image_bytes(brightness=200)
        result = check_image_quality(img_bytes)
        self.assertFalse(result['is_dark'])
        self.assertGreater(result['quality_score'], 50)

    def test_dark_image_detected(self):
        from apps.photos.ai_service import check_image_quality
        img_bytes = _make_dark_image_bytes()
        result = check_image_quality(img_bytes)
        self.assertTrue(result['is_dark'])

    def test_blurry_image_detected(self):
        from apps.photos.ai_service import check_image_quality
        img_bytes = _make_blurry_image_bytes()
        result = check_image_quality(img_bytes)
        self.assertTrue(result['is_blurry'])

    def test_result_has_required_keys(self):
        from apps.photos.ai_service import check_image_quality
        img_bytes = _make_bright_image_bytes()
        result = check_image_quality(img_bytes)
        for key in ('quality_score', 'is_blurry', 'is_dark', 'needs_retake', 'reason'):
            self.assertIn(key, result)

    def test_quality_score_range(self):
        from apps.photos.ai_service import check_image_quality
        img_bytes = _make_bright_image_bytes()
        result = check_image_quality(img_bytes)
        self.assertGreaterEqual(result['quality_score'], 0)
        self.assertLessEqual(result['quality_score'], 100)


# ─────────────────────────────────────────────────────────────
# 3. classify_photo_stage() — 설치 전/후 분류
# ─────────────────────────────────────────────────────────────
class PhotoStageClassifyTest(TestCase):
    """설치 전/후/기타 분류"""

    def test_function_importable(self):
        try:
            from apps.photos.ai_service import classify_photo_stage
        except ImportError:
            self.fail('classify_photo_stage 가 ai_service.py에 없습니다.')

    @patch('apps.photos.ai_service._call_claude_vision')
    def test_claude_before_result(self, mock_claude):
        """Claude API가 '설치 전' 반환 시 before"""
        mock_claude.return_value = {
            'stage': 'before', 'confidence': 0.92,
            'reason': '장비가 설치되지 않은 빈 랙 사진'
        }
        from apps.photos.ai_service import classify_photo_stage
        img_bytes = _make_bright_image_bytes()
        result = classify_photo_stage(img_bytes, filename='before_work.jpg')
        self.assertEqual(result['stage'], 'before')
        self.assertGreater(result['confidence'], 0.8)

    @patch('apps.photos.ai_service._call_claude_vision')
    def test_claude_after_result(self, mock_claude):
        """Claude API가 '설치 후' 반환 시 after"""
        mock_claude.return_value = {
            'stage': 'after', 'confidence': 0.95,
            'reason': '스위치가 설치된 완료 사진'
        }
        from apps.photos.ai_service import classify_photo_stage
        img_bytes = _make_bright_image_bytes()
        result = classify_photo_stage(img_bytes, filename='after_work.jpg')
        self.assertEqual(result['stage'], 'after')

    @patch('apps.photos.ai_service._call_claude_vision', side_effect=Exception('API 불가'))
    def test_fallback_to_filename_when_claude_fails(self, mock_claude):
        """Claude API 실패 시 파일명 폴백"""
        from apps.photos.ai_service import classify_photo_stage
        img_bytes = _make_bright_image_bytes()
        result = classify_photo_stage(img_bytes, filename='before_작업전.jpg')
        # 파일명에 'before' 포함 → before로 폴백
        self.assertIn(result['stage'], ['before', 'other'])
        self.assertEqual(result['method'], 'fallback_filename')

    def test_result_has_required_keys(self):
        from apps.photos.ai_service import classify_photo_stage
        with patch('apps.photos.ai_service._call_claude_vision') as mock:
            mock.return_value = {'stage': 'other', 'confidence': 0.5, 'reason': ''}
            img_bytes = _make_bright_image_bytes()
            result = classify_photo_stage(img_bytes, filename='test.jpg')
            for key in ('stage', 'confidence', 'method'):
                self.assertIn(key, result)


# ─────────────────────────────────────────────────────────────
# 4. detect_defects() — 불량 설치 감지
# ─────────────────────────────────────────────────────────────
class DefectDetectionTest(TestCase):
    """불량 설치 감지 (케이블 정리, 레이블 부착)"""

    def test_function_importable(self):
        try:
            from apps.photos.ai_service import detect_defects
        except ImportError:
            self.fail('detect_defects 가 ai_service.py에 없습니다.')

    @patch('apps.photos.ai_service._call_claude_vision')
    def test_cable_messy_detected(self, mock_claude):
        """케이블 정리 불량 감지"""
        mock_claude.return_value = {
            'defects': {
                'cable_messy': True,
                'label_missing': False,
                'improper_mounting': False,
            },
            'defect_score': 0.8,
            'details': '케이블이 정리되지 않고 뒤엉켜 있음',
        }
        from apps.photos.ai_service import detect_defects
        img_bytes = _make_bright_image_bytes()
        result = detect_defects(img_bytes)
        self.assertTrue(result['defects'].get('cable_messy'))

    @patch('apps.photos.ai_service._call_claude_vision')
    def test_label_missing_detected(self, mock_claude):
        """레이블 미부착 감지"""
        mock_claude.return_value = {
            'defects': {
                'cable_messy': False,
                'label_missing': True,
                'improper_mounting': False,
            },
            'defect_score': 0.7,
            'details': '포트 레이블이 부착되지 않음',
        }
        from apps.photos.ai_service import detect_defects
        img_bytes = _make_bright_image_bytes()
        result = detect_defects(img_bytes)
        self.assertTrue(result['defects'].get('label_missing'))

    @patch('apps.photos.ai_service._call_claude_vision', side_effect=Exception('API 불가'))
    def test_fallback_when_claude_fails(self, mock_claude):
        """Claude API 실패 시 빈 불량 반환 (정상 처리)"""
        from apps.photos.ai_service import detect_defects
        img_bytes = _make_bright_image_bytes()
        result = detect_defects(img_bytes)
        self.assertIn('defects', result)
        self.assertIsInstance(result['defects'], dict)

    def test_result_has_required_keys(self):
        from apps.photos.ai_service import detect_defects
        with patch('apps.photos.ai_service._call_claude_vision') as mock:
            mock.return_value = {
                'defects': {'cable_messy': False, 'label_missing': False},
                'defect_score': 0.0,
                'details': '',
            }
            img_bytes = _make_bright_image_bytes()
            result = detect_defects(img_bytes)
            for key in ('defects', 'defect_score', 'has_defect'):
                self.assertIn(key, result)


# ─────────────────────────────────────────────────────────────
# 5~6. analyze_photo() — 종합 AI 분석 + needs_retake
# ─────────────────────────────────────────────────────────────
class AnalyzePhotoTest(PhotoAIFixtureMixin, TestCase):
    """종합 AI 분석 — 품질+분류+불량 통합"""

    def test_function_importable(self):
        try:
            from apps.photos.ai_service import analyze_photo
        except ImportError:
            self.fail('analyze_photo 가 ai_service.py에 없습니다.')

    @patch('apps.photos.ai_service._call_claude_vision')
    def test_good_photo_not_marked_retake(self, mock_claude):
        """품질 좋은 사진은 needs_retake=False"""
        mock_claude.return_value = {
            'stage': 'after', 'confidence': 0.9, 'reason': '완료 사진',
            'defects': {'cable_messy': False, 'label_missing': False},
            'defect_score': 0.0, 'details': '',
        }
        from apps.photos.ai_service import analyze_photo
        photo = self._make_photo()
        with open(photo.image.path, 'rb') as f:
            img_bytes = f.read()
        result = analyze_photo(photo, img_bytes)
        self.assertFalse(result['needs_retake'])

    @patch('apps.photos.ai_service._call_claude_vision')
    def test_dark_photo_marked_retake(self, mock_claude):
        """어두운 사진은 needs_retake=True"""
        mock_claude.return_value = {
            'stage': 'other', 'confidence': 0.5, 'reason': '',
            'defects': {}, 'defect_score': 0.0, 'details': '',
        }
        from apps.photos.ai_service import analyze_photo
        photo = self._make_photo()
        dark_bytes = _make_dark_image_bytes()
        result = analyze_photo(photo, dark_bytes)
        self.assertTrue(result['needs_retake'])
        self.assertIn('어두', result['retake_reason'])

    @patch('apps.photos.ai_service._call_claude_vision')
    def test_analyze_saves_to_photo(self, mock_claude):
        """분석 결과가 Photo 모델에 저장됨"""
        mock_claude.return_value = {
            'stage': 'before', 'confidence': 0.88, 'reason': '작업 전',
            'defects': {'cable_messy': False, 'label_missing': False},
            'defect_score': 0.0, 'details': '',
        }
        from apps.photos.ai_service import analyze_photo
        photo = self._make_photo()
        with open(photo.image.path, 'rb') as f:
            img_bytes = f.read()
        analyze_photo(photo, img_bytes, save=True)
        photo.refresh_from_db()
        self.assertIsNotNone(photo.quality_score)
        self.assertEqual(photo.ai_stage, 'before')

    @patch('apps.photos.ai_service._call_claude_vision')
    def test_defect_photo_flagged(self, mock_claude):
        """불량 감지 사진은 defect_flags에 기록"""
        mock_claude.return_value = {
            'stage': 'after', 'confidence': 0.9, 'reason': '',
            'defects': {'cable_messy': True, 'label_missing': True},
            'defect_score': 0.8, 'details': '불량',
        }
        from apps.photos.ai_service import analyze_photo
        photo = self._make_photo()
        with open(photo.image.path, 'rb') as f:
            img_bytes = f.read()
        result = analyze_photo(photo, img_bytes, save=True)
        self.assertTrue(result['has_defect'])
        photo.refresh_from_db()
        self.assertTrue(photo.defect_flags.get('cable_messy'))


# ─────────────────────────────────────────────────────────────
# 7. POST /api/photos/{id}/analyze/ API
# ─────────────────────────────────────────────────────────────
class PhotoAnalyzeAPITest(PhotoAIFixtureMixin, TestCase):
    """사진 AI 분석 트리거 API"""

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.worker)

    @patch('apps.photos.ai_service._call_claude_vision')
    def test_analyze_api_returns_200(self, mock_claude):
        mock_claude.return_value = {
            'stage': 'after', 'confidence': 0.9, 'reason': '',
            'defects': {'cable_messy': False, 'label_missing': False},
            'defect_score': 0.0, 'details': '',
        }
        photo = self._make_photo()
        resp = self.client.post(f'/api/photos/photos/{photo.pk}/analyze/')
        self.assertEqual(resp.status_code, 200)

    @patch('apps.photos.ai_service._call_claude_vision')
    def test_analyze_api_returns_result(self, mock_claude):
        mock_claude.return_value = {
            'stage': 'before', 'confidence': 0.85, 'reason': '설치 전',
            'defects': {'cable_messy': False, 'label_missing': False},
            'defect_score': 0.0, 'details': '',
        }
        photo = self._make_photo()
        resp = self.client.post(f'/api/photos/photos/{photo.pk}/analyze/')
        data = resp.json()
        for key in ('quality_score', 'ai_stage', 'needs_retake'):
            self.assertIn(key, data)

    @patch('apps.photos.ai_service._call_claude_vision')
    def test_analyze_api_updates_photo(self, mock_claude):
        mock_claude.return_value = {
            'stage': 'after', 'confidence': 0.92, 'reason': '',
            'defects': {}, 'defect_score': 0.0, 'details': '',
        }
        photo = self._make_photo()
        self.client.post(f'/api/photos/photos/{photo.pk}/analyze/')
        photo.refresh_from_db()
        self.assertIsNotNone(photo.quality_score)

    def test_analyze_requires_auth(self):
        photo = self._make_photo()
        c = APIClient()
        resp = c.post(f'/api/photos/photos/{photo.pk}/analyze/')
        self.assertIn(resp.status_code, [401, 403])


# ─────────────────────────────────────────────────────────────
# 8. GET /api/photos/quality-issues/ API
# ─────────────────────────────────────────────────────────────
class PhotoQualityIssuesAPITest(PhotoAIFixtureMixin, TestCase):
    """재촬영 필요 사진 목록 API"""

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.worker)

    def test_quality_issues_api_200(self):
        resp = self.client.get('/api/photos/photos/quality-issues/')
        self.assertEqual(resp.status_code, 200)

    def test_quality_issues_shows_retake_photos(self):
        """needs_retake=True 사진만 반환"""
        from django.core.files.base import ContentFile
        # needs_retake=True 사진 생성
        photo = self._make_photo()
        photo.needs_retake = True
        photo.retake_reason = '어두운 사진'
        photo.save()

        resp = self.client.get('/api/photos/photos/quality-issues/')
        data = resp.json()
        results = data.get('results', data) if isinstance(data, dict) else data
        ids = [r['id'] for r in (results if isinstance(results, list) else [])]
        self.assertIn(photo.pk, ids)

    def test_quality_issues_excludes_good_photos(self):
        """needs_retake=False 사진은 제외"""
        photo = self._make_photo()
        photo.needs_retake = False
        photo.save()
        resp = self.client.get('/api/photos/photos/quality-issues/')
        data = resp.json()
        results = data.get('results', data) if isinstance(data, dict) else data
        if isinstance(results, list):
            ids = [r['id'] for r in results]
            self.assertNotIn(photo.pk, ids)


# ─────────────────────────────────────────────────────────────
# 9. Claude API 장애 시 폴백 동작
# ─────────────────────────────────────────────────────────────
class ClaudeAPIFallbackTest(TestCase):
    """Claude API 장애 시 전체 파이프라인 폴백 동작"""

    @patch('apps.photos.ai_service._call_claude_vision', side_effect=Exception('연결 불가'))
    def test_full_analyze_survives_claude_failure(self, mock_claude):
        """Claude API 완전 실패 시에도 분석 결과 반환 (폴백)"""
        from apps.photos.ai_service import check_image_quality, classify_photo_stage
        img_bytes = _make_bright_image_bytes()

        quality = check_image_quality(img_bytes)
        stage = classify_photo_stage(img_bytes, filename='test_before.jpg')

        self.assertIsNotNone(quality)
        self.assertIsNotNone(stage)
        self.assertEqual(stage['method'], 'fallback_filename')

    def test_call_claude_vision_function_exists(self):
        """_call_claude_vision 함수가 ai_service에 존재해야 함"""
        try:
            from apps.photos.ai_service import _call_claude_vision
        except ImportError:
            self.fail('_call_claude_vision 이 ai_service.py에 없습니다.')
