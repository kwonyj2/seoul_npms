"""
DRF 커스텀 예외 핸들러 — 표준 에러 응답 포맷
API 에러를 {'error': '...', 'detail': ...} 형태로 통일한다.
"""
from rest_framework.views import exception_handler
from rest_framework.response import Response


def custom_exception_handler(exc, context):
    """
    DRF 기본 핸들러를 먼저 실행한 뒤, 응답을 표준 포맷으로 래핑한다.

    성공 시 반환 구조:
        {
            "error": "<사람이 읽을 수 있는 오류 명칭>",
            "detail": <DRF 기본 detail 값>
        }

    DRF가 처리하지 못하는 예외(비-APIException)는 None 반환 → Django 500 핸들러에 위임.
    """
    response = exception_handler(exc, context)

    if response is None:
        # DRF가 처리하지 않는 예외 (ValueError, RuntimeError 등)
        return None

    # 오류 이름 도출: 상태코드 → 공통 명칭 매핑
    _STATUS_NAMES = {
        400: 'Bad Request',
        401: 'Unauthorized',
        403: 'Forbidden',
        404: 'Not Found',
        405: 'Method Not Allowed',
        409: 'Conflict',
        429: 'Too Many Requests',
        500: 'Internal Server Error',
    }
    error_name = _STATUS_NAMES.get(response.status_code, 'Error')

    response.data = {
        'error': error_name,
        'detail': response.data,
    }
    return response
