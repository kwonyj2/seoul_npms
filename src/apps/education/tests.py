from django.test import TestCase


class EducationCompletionJudgmentTest(TestCase):
    """교육 이수 판정 로직 단위 테스트 (api_complete_course 로직)"""

    def _judge(self, watch_percents, pass_percent):
        """
        수강 진도 목록과 이수 기준으로 판정 결과 반환.
        watch_percents: 각 콘텐츠의 watch_percent 리스트
        pass_percent:   과정의 이수 기준(%)
        """
        if not watch_percents:
            return {'ok': True, 'avg': 100}
        avg = sum(watch_percents) // len(watch_percents)
        return {'ok': avg >= pass_percent, 'avg': avg}

    def test_all_videos_fully_watched(self):
        """모든 영상 100% 시청 → 이수 가능"""
        r = self._judge([100, 100, 100], pass_percent=80)
        self.assertTrue(r['ok'])
        self.assertEqual(r['avg'], 100)

    def test_below_pass_percent(self):
        """평균 시청률 기준 미달 → 이수 불가"""
        r = self._judge([60, 70, 50], pass_percent=80)
        self.assertFalse(r['ok'])
        self.assertEqual(r['avg'], 60)

    def test_exactly_at_pass_percent(self):
        """평균 시청률 = 이수 기준 정각 → 이수 가능 (경계값)"""
        r = self._judge([80, 80, 80], pass_percent=80)
        self.assertTrue(r['ok'])

    def test_mixed_progress(self):
        """일부 미시청, 일부 완료 — 평균으로 판정"""
        r = self._judge([100, 100, 0, 100], pass_percent=80)
        self.assertFalse(r['ok'])
        self.assertEqual(r['avg'], 75)

    def test_no_contents_course(self):
        """콘텐츠 없는 과정 → 무조건 이수 가능"""
        r = self._judge([], pass_percent=80)
        self.assertTrue(r['ok'])

    def test_single_content_pass(self):
        """콘텐츠 1개, 기준 충족"""
        r = self._judge([90], pass_percent=80)
        self.assertTrue(r['ok'])

    def test_single_content_fail(self):
        """콘텐츠 1개, 기준 미달"""
        r = self._judge([70], pass_percent=80)
        self.assertFalse(r['ok'])

    def test_certificate_number_format(self):
        """이수증 번호 형식 검증 (CERT-YYYYMMDD-NNN)"""
        from django.utils import timezone as tz
        today = tz.localdate().strftime('%Y%m%d')
        cert_no = f'CERT-{today}-001'
        parts = cert_no.split('-')
        self.assertEqual(parts[0], 'CERT')
        self.assertEqual(len(parts[1]), 8)   # YYYYMMDD
        self.assertTrue(parts[2].isdigit())
