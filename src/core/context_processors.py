from django.conf import settings


def global_settings(request):
    return {
        'VWORLD_API_KEY': getattr(settings, 'VWORLD_API_KEY', ''),
        'SITE_NAME': 'NPMS - 학교 네트워크 장애관리 시스템',
    }


def user_access(request):
    """현재 사용자의 모듈별 접근 권한을 템플릿에 제공"""
    if not request.user.is_authenticated:
        return {'user_access': {}}
    from core.modules import MODULE_REGISTRY, can_access
    access = {key: can_access(request.user.role, key) for key in MODULE_REGISTRY}
    return {'user_access': access}
