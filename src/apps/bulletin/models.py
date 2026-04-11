"""
bulletin 앱 모델
업무공지 / 자료실 게시판
"""
import os
from django.db import models
from django.conf import settings


def attachment_upload_path(instance, filename):
    return f'bulletin/{instance.post.category}/{instance.post.id}/{filename}'


class Post(models.Model):
    CATEGORY_CHOICES = [
        ('notice',    '업무공지'),
        ('data_room', '자료실'),
    ]
    category    = models.CharField('분류', max_length=20, choices=CATEGORY_CHOICES, default='notice')
    title       = models.CharField('제목', max_length=200)
    content     = models.TextField('내용', blank=True)
    author      = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True,
        related_name='bulletin_posts', verbose_name='작성자'
    )
    is_pinned   = models.BooleanField('상단고정', default=False)
    is_active   = models.BooleanField('활성', default=True)
    view_count  = models.PositiveIntegerField('조회수', default=0)
    created_at  = models.DateTimeField('작성일시', auto_now_add=True)
    updated_at  = models.DateTimeField('수정일시', auto_now=True)

    class Meta:
        db_table = 'bulletin_posts'
        verbose_name = '게시글'
        ordering = ['-is_pinned', '-created_at']

    def __str__(self):
        return f'[{self.get_category_display()}] {self.title}'


class Attachment(models.Model):
    post       = models.ForeignKey(Post, on_delete=models.CASCADE,
                                   related_name='attachments', verbose_name='게시글')
    file       = models.FileField('파일', upload_to=attachment_upload_path)
    filename   = models.CharField('파일명', max_length=255)
    filesize   = models.PositiveIntegerField('파일크기(bytes)', default=0)
    uploaded_at = models.DateTimeField('업로드일시', auto_now_add=True)

    class Meta:
        db_table = 'bulletin_attachments'
        verbose_name = '첨부파일'

    def __str__(self):
        return self.filename

    def save(self, *args, **kwargs):
        if self.file and not self.filename:
            self.filename = os.path.basename(self.file.name)
        if self.file and not self.filesize:
            try:
                self.filesize = self.file.size
            except Exception:
                pass
        super().save(*args, **kwargs)
