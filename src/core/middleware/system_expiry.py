"""
시스템 만료일 미들웨어
- 만료 후: superadmin만 접속 가능, 나머지 사용자는 만료 안내 페이지로 리다이렉트
- superadmin이 만료일 연장 시 즉시 정상 가동
"""
from django.http import JsonResponse
from django.shortcuts import redirect
from django.utils import timezone


class SystemExpiryMiddleware:
    # 만료 시에도 허용하는 URL (로그인/로그아웃/정적파일/API 만료확인)
    EXEMPT_PATHS = [
        '/npms/accounts/login/',
        '/npms/accounts/logout/',
        '/npms/static/',
        '/npms/api/accounts/token/',
        '/npms/api/sysconfig/system-expiry/',
    ]

    def __init__(self, get_response):
        self.get_response = get_response
        self._cache_expiry = None
        self._cache_time = None

    def __call__(self, request):
        # 정적 파일 등 exempt 경로는 패스
        path = request.path
        if any(path.startswith(p) for p in self.EXEMPT_PATHS):
            return self.get_response(request)

        # 5초 캐시 — 매 요청마다 DB 조회 방지
        now = timezone.now()
        if self._cache_time is None or (now - self._cache_time).seconds > 5:
            from apps.sysconfig.models import SystemExpiry
            self._cache_expiry = SystemExpiry.is_expired()
            self._cache_time = now

        if self._cache_expiry and request.user.is_authenticated:
            user_role = getattr(request.user, 'role', '')
            if user_role != 'superadmin':
                # API 요청이면 JSON, 아니면 로그아웃
                if path.startswith('/npms/api/'):
                    return JsonResponse({
                        'error': '시스템 서비스 기간이 만료되었습니다. 관리자에게 문의하세요.'
                    }, status=403)
                from django.contrib.auth import logout
                logout(request)
                from django.contrib import messages
                messages.error(request, '시스템 서비스 기간이 만료되었습니다. 관리자에게 문의하세요.')
                return redirect('/npms/accounts/login/')

        return self.get_response(request)
