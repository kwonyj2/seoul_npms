from django.contrib import admin
from .models import SupportCenter, SchoolType, School, SchoolBuilding, SchoolFloor, SchoolRoom, SchoolContact, SchoolNetwork

@admin.register(SupportCenter)
class SupportCenterAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'phone', 'is_active')

@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = ('name', 'support_center', 'school_type', 'address', 'is_active')
    list_filter = ('support_center', 'school_type', 'is_active')
    search_fields = ('name', 'address', 'code')
    list_select_related = ('support_center', 'school_type')

@admin.register(SchoolBuilding)
class SchoolBuildingAdmin(admin.ModelAdmin):
    list_display = ('school', 'name', 'floors')
    list_select_related = ('school',)

admin.site.register(SchoolType)
admin.site.register(SchoolFloor)
admin.site.register(SchoolRoom)
admin.site.register(SchoolContact)
admin.site.register(SchoolNetwork)
