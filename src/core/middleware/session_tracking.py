"""
NPMS 접속 세션 추적 미들웨어
- 인증된 사용자의 모든 요청마다 UserSession.last_active 갱신
- 템플릿 페이지 요청 시 current_page(한글 화면명) 갱신
"""
import re
from django.utils import timezone

# URL 경로 → 한글 화면명 (순서 중요: 구체적인 것 먼저)
PAGE_MAP = [
    (r'^/npms/$',                    '대시보드'),
    (r'^/npms/dashboard',            '대시보드'),
    (r'^/npms/incidents/create',     '장애접수'),
    (r'^/npms/incidents/\d+/',       '장애상세'),
    (r'^/npms/incidents',            '장애목록'),
    (r'^/npms/schools/\d+/',         '학교상세'),
    (r'^/npms/schools',              '학교관리'),
    (r'^/npms/workforce',            '인력관리'),
    (r'^/npms/accounts',             '사용자관리'),
    (r'^/npms/materials',            '자재관리'),
    (r'^/npms/assets',               '장비관리'),
    (r'^/npms/reports',              '보고서'),
    (r'^/npms/nas',                  '파일관리'),
    (r'^/npms/photos',               '사진관리'),
    (r'^/npms/network',              '네트워크'),
    (r'^/npms/statistics',           '통계'),
    (r'^/npms/progress',             '진척관리'),
    (r'^/npms/bulletin',             '게시판'),
    (r'^/npms/admin/data-management','데이터관리'),
    (r'^/npms/admin',                '관리자'),
]

_COMPILED = [(re.compile(p), name) for p, name in PAGE_MAP]


def _resolve_page_name(path):
    for pattern, name in _COMPILED:
        if pattern.match(path):
            return name
    return None


class SessionTrackingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # 인증 사용자 + /npms/ 경로만 추적
        if (
            request.user.is_authenticated
            and request.path.startswith('/npms/')
            and hasattr(request, 'session')
            and request.session.session_key
        ):
            try:
                from apps.accounts.models import UserSession

                is_api = '/api/' in request.path or request.path.startswith('/npms/api')
                page_name = None if is_api else _resolve_page_name(request.path)

                session_key = request.session.session_key
                now = timezone.now()

                if page_name:
                    # 페이지 요청: current_page + last_active 갱신
                    updated = UserSession.objects.filter(
                        session_key=session_key
                    ).update(current_page=page_name, last_active=now, is_active=True)
                else:
                    # API 등 배경 요청: last_active만 갱신
                    updated = UserSession.objects.filter(
                        session_key=session_key
                    ).update(last_active=now, is_active=True)

                # 세션 레코드 없으면 신규 생성 (미들웨어 등록 전 로그인한 사용자 대응)
                if not updated:
                    UserSession.objects.update_or_create(
                        session_key=session_key,
                        defaults={
                            'user':         request.user,
                            'ip_address':   request.META.get('REMOTE_ADDR'),
                            'user_agent':   request.META.get('HTTP_USER_AGENT', '')[:200],
                            'current_page': page_name or '접속중',
                            'is_active':    True,
                        }
                    )
            except Exception:
                pass  # DB 오류가 응답을 방해하지 않도록

        return response
