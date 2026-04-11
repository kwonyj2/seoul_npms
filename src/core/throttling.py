"""커스텀 레이트 리미팅 Throttle 클래스"""
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class LoginRateThrottle(AnonRateThrottle):
    """로그인 API: IP당 분당 10회"""
    scope = 'login'
    rate = '10/min'


class UploadRateThrottle(UserRateThrottle):
    """파일 업로드: 사용자당 시간당 100회"""
    scope = 'upload'
    rate = '100/hour'


class PDFGenerateThrottle(UserRateThrottle):
    """PDF 생성: 사용자당 분당 5회"""
    scope = 'pdf'
    rate = '5/min'
