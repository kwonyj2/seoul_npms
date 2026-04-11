from django.contrib import admin
from .models import Post, Attachment


class AttachmentInline(admin.TabularInline):
    model  = Attachment
    extra  = 0
    fields = ['filename', 'filesize', 'file']


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display  = ['category', 'title', 'author', 'is_pinned', 'view_count', 'created_at']
    list_filter   = ['category', 'is_pinned', 'is_active']
    search_fields = ['title', 'content']
    inlines       = [AttachmentInline]
