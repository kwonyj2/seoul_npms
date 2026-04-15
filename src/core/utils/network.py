"""네트워크 유틸리티 — 실제 클라이언트 IP 추출 등"""


def get_client_ip(request) -> str:
    """nginx 프록시 뒤에서 실제 클라이언트 IP를 추출한다.
    우선순위: X-Forwarded-For → X-Real-IP → REMOTE_ADDR
    """
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        # X-Forwarded-For: client, proxy1, proxy2 → 첫 번째가 실제 클라이언트
        return xff.split(',')[0].strip()
    xri = request.META.get('HTTP_X_REAL_IP')
    if xri:
        return xri.strip()
    return request.META.get('REMOTE_ADDR', '')
