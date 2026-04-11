from django.contrib import admin
from .models import EducationCategory, EducationCourse, EducationContent, EducationCompletion

@admin.register(EducationCategory)
class EducationCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'icon', 'color', 'order', 'is_active')
    list_editable = ('order', 'is_active')

@admin.register(EducationCourse)
class EducationCourseAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'instructor', 'duration_minutes', 'is_required', 'is_active')
    list_filter = ('category', 'is_required', 'is_active')

@admin.register(EducationContent)
class EducationContentAdmin(admin.ModelAdmin):
    list_display = ('title', 'course', 'content_type', 'duration_seconds', 'order')
    list_filter = ('content_type', 'course__category')

@admin.register(EducationCompletion)
class EducationCompletionAdmin(admin.ModelAdmin):
    list_display = ('certificate_no', 'user', 'course', 'completed_at', 'score')
    list_filter = ('course__category',)
    readonly_fields = ('certificate_no',)
