from functools import wraps
from rest_framework.permissions import BasePermission


class IsSuperAdmin(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'superadmin'

class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in ('superadmin', 'admin')

class IsWorker(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in ('superadmin', 'admin', 'worker')

class IsCustomer(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated


def module_required(module_key):
    """모듈 접근 권한 데코레이터 — can_access() 기반"""
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                from django.shortcuts import redirect
                return redirect('/npms/accounts/login/')
            from core.modules import can_access
            if not can_access(request.user.role, module_key):
                from django.http import HttpResponse
                return HttpResponse(
                    '<div style="font-family:sans-serif;padding:60px;text-align:center;">'
                    '<h2>접근 권한이 없습니다</h2>'
                    '<p style="color:#6c757d">이 페이지에 접근할 수 있는 권한이 없습니다.</p>'
                    '<a href="/npms/" style="color:#2563eb">대시보드로 돌아가기</a>'
                    '</div>',
                    status=403
                )
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator
