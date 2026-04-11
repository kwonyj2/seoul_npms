from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, UserSession, UserActivityLog, LoginHistory

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('username', 'name', 'role', 'support_center', 'is_active', 'service_expiry')
    list_filter = ('role', 'is_active', 'support_center')
    search_fields = ('username', 'name', 'email', 'phone')
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('개인정보', {'fields': ('name', 'email', 'phone', 'profile_image')}),
        ('역할/소속', {'fields': ('role', 'support_center', 'service_expiry')}),
        ('자택주소', {'fields': ('home_address', 'home_lat', 'home_lng')}),
        ('권한', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
    )
    add_fieldsets = (
        (None, {'fields': ('username', 'email', 'name', 'password1', 'password2', 'role')}),
    )
    ordering = ('-created_at',)

@admin.register(UserActivityLog)
class UserActivityLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'action', 'target', 'created_at')
    list_filter = ('action',)
    readonly_fields = ('user', 'action', 'target', 'detail', 'ip_address', 'created_at')
