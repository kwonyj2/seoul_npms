"""
IP 차단 미들웨어
- BlockedIP에 등록된 IP → 403 응답
- 로그인 실패 임계값 초과 시 자동 차단
"""
import datetime
import logging

from django.http import JsonResponse
from django.utils import timezone

from core.utils.network import get_client_ip

logger = logging.getLogger('security')


class IPBlockMiddleware:
    """요청 IP가 차단 목록에 있으면 403 반환"""

    def __init__(self, get_response):
        self.get_response = get_response
        # 캐시: {ip: expires_at} — DB 조회 최소화
        self._cache = {}
        self._cache_ts = None
        self._whitelist = set()

    def _refresh_cache(self):
        """5초마다 캐시 갱신"""
        now = timezone.now()
        if self._cache_ts and (now - self._cache_ts).total_seconds() < 5:
            return
        try:
            from apps.sysconfig.security_models import BlockedIP, WhitelistedIP
            self._cache = {}
            for b in BlockedIP.objects.all():
                if b.is_active:
                    self._cache[b.ip_address] = True
            self._whitelist = set(
                WhitelistedIP.objects.values_list('ip_address', flat=True)
            )
            self._cache_ts = now
        except Exception:
            pass

    def __call__(self, request):
        ip = get_client_ip(request)

        self._refresh_cache()

        # 화이트리스트 통과
        if ip in self._whitelist:
            return self.get_response(request)

        # 차단 IP 확인
        if ip in self._cache:
            logger.warning(f'[IP_BLOCK] 차단된 IP 접근 시도: {ip} → {request.path}')
            # JSON API 요청이면 JSON 응답
            if request.path.startswith('/npms/api/') or request.headers.get('Accept', '').startswith('application/json'):
                return JsonResponse(
                    {'error': '접근이 차단된 IP입니다.', 'ip': ip},
                    status=403
                )
            # 일반 페이지는 간단한 HTML
            return JsonResponse(
                {'error': '접근이 차단되었습니다.'},
                status=403
            )

        response = self.get_response(request)

        # 로그인 실패 시 자동 차단 체크
        if (request.path.endswith('/login/') and
                request.method == 'POST' and
                response.status_code in (200, 302) and
                not request.user.is_authenticated):
            self._check_auto_block(ip)

        return response

    def _check_auto_block(self, ip):
        """로그인 실패 누적 → 자동 차단"""
        try:
            from apps.sysconfig.security_models import (
                SecurityConfig, BlockedIP, WhitelistedIP, BlockLog, SecurityEvent
            )
            from apps.accounts.models import LoginHistory

            if not SecurityConfig.get_bool('auto_block_enabled'):
                return
            if WhitelistedIP.objects.filter(ip_address=ip).exists():
                return
            if BlockedIP.objects.filter(ip_address=ip).exists():
                return

            threshold = SecurityConfig.get_int('block_threshold', 10)
            window_min = SecurityConfig.get_int('block_window_min', 30)
            duration_min = SecurityConfig.get_int('block_duration_min', 60)
            perm_threshold = SecurityConfig.get_int('permanent_threshold', 50)

            since = timezone.now() - datetime.timedelta(minutes=window_min)
            fail_count = LoginHistory.objects.filter(
                ip_address=ip, success=False, created_at__gte=since
            ).count()

            if fail_count >= threshold:
                is_perm = fail_count >= perm_threshold
                BlockedIP.objects.update_or_create(
                    ip_address=ip,
                    defaults={
                        'reason': 'brute_force',
                        'description': f'{window_min}분 내 {fail_count}회 로그인 실패',
                        'is_permanent': is_perm,
                        'auto_blocked': True,
                        'fail_count': fail_count,
                        'expires_at': None if is_perm else (
                            timezone.now() + datetime.timedelta(minutes=duration_min)
                        ),
                    }
                )
                BlockLog.objects.create(
                    ip_address=ip, action='block',
                    reason=f'자동차단: {fail_count}회 실패 ({window_min}분)',
                )
                SecurityEvent.objects.create(
                    event_type='ip_blocked',
                    severity='high' if is_perm else 'medium',
                    ip_address=ip,
                    description=f'자동 IP 차단: {fail_count}회 로그인 실패 → {"영구" if is_perm else f"{duration_min}분"} 차단',
                )
                logger.warning(f'[AUTO_BLOCK] {ip} 차단됨 — {fail_count}회 실패')
        except Exception as e:
            logger.debug(f'auto_block 오류: {e}')
