"""
커스텀 에러 핸들러 — 404 / 500
API 요청이면 JSON, 그 외엔 HTML 응답 반환하고 apps.errors 로거에 기록
"""
import logging
from django.http import JsonResponse, HttpResponse
from django.template.loader import render_to_string

logger = logging.getLogger('apps.errors')


def _is_api(request):
    """API 요청 여부 판별 (경로 또는 Accept 헤더 기준)"""
    return (
        request.path.startswith('/api/')
        or request.path.startswith('/npms/api/')
        or 'application/json' in request.META.get('HTTP_ACCEPT', '')
    )


def custom_404(request, exception=None):
    logger.warning('404 Not Found: %s %s', request.method, request.path)
    if _is_api(request):
        return JsonResponse(
            {'error': 'Not Found', 'path': request.path},
            status=404,
        )
    try:
        html = render_to_string('errors/404.html', request=request)
    except Exception:
        html = '<h1>404 — 페이지를 찾을 수 없습니다</h1>'
    return HttpResponse(html, status=404)


def custom_500(request):
    logger.error('500 Internal Server Error: %s %s', request.method, request.path)
    if _is_api(request):
        return JsonResponse(
            {'error': 'Internal Server Error'},
            status=500,
        )
    try:
        html = render_to_string('errors/500.html', request=request)
    except Exception:
        html = '<h1>500 — 서버 오류가 발생했습니다</h1>'
    return HttpResponse(html, status=500)
