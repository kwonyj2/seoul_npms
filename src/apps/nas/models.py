"""
nas 앱 모델
NAS 파일 시스템 (Synology FileStation 스타일)
"""
from django.db import models


class Folder(models.Model):
    ACCESS_CHOICES = [
        ('public',     '전체 공개'),
        ('admin',      '관리자 이상'),
        ('superadmin', '슈퍼어드민 전용'),
    ]

    name         = models.CharField('폴더명', max_length=255)
    parent       = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='children', verbose_name='상위폴더')
    school       = models.ForeignKey('schools.School', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='학교', related_name='nas_folders')
    full_path    = models.TextField('전체경로', db_index=True)
    is_system    = models.BooleanField('시스템폴더', default=False)
    access_level = models.CharField('접근권한', max_length=20, choices=ACCESS_CHOICES, default='public')
    created_by   = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, verbose_name='생성자')
    created_at   = models.DateTimeField('생성일시', auto_now_add=True)

    class Meta:
        db_table = 'nas_folders'
        verbose_name = 'NAS 폴더'
        unique_together = [['parent', 'name']]

    def __str__(self):
        return self.full_path


class File(models.Model):
    CATEGORY_CHOICES = [
        ('report',    '산출물'),
        ('photo',     '작업이미지'),
        ('incident',  '장애처리보고서'),
        ('regular',   '정기점검'),
        ('cable',     '케이블공사'),
        ('switch',    '스위치설치'),
        ('other',     '기타'),
    ]
    folder       = models.ForeignKey(Folder, on_delete=models.CASCADE, verbose_name='폴더', related_name='files')
    name         = models.CharField('파일명', max_length=255)
    original_name= models.CharField('원본파일명', max_length=255)
    file_path    = models.TextField('저장경로')
    file_size    = models.BigIntegerField('파일크기(bytes)', default=0)
    mime_type    = models.CharField('MIME유형', max_length=100, blank=True)
    category     = models.CharField('분류', max_length=20, choices=CATEGORY_CHOICES, default='other')
    school       = models.ForeignKey('schools.School', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='학교')
    description  = models.TextField('설명', blank=True)
    ocr_text     = models.TextField('OCR 추출 텍스트', blank=True)
    uploaded_by  = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, verbose_name='업로더')
    uploaded_at  = models.DateTimeField('업로드일시', auto_now_add=True)
    # 휴지통
    is_deleted   = models.BooleanField('휴지통', default=False)
    deleted_at   = models.DateTimeField('삭제일시', null=True, blank=True)
    deleted_by   = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='deleted_files', verbose_name='삭제자')
    original_path = models.TextField('원본경로', blank=True)

    class Meta:
        db_table = 'nas_files'
        verbose_name = 'NAS 파일'
        unique_together = [['folder', 'name']]
        ordering = ['-uploaded_at']

    def __str__(self):
        return f'{self.folder.full_path}/{self.name}'


class FilePermission(models.Model):
    PERM_CHOICES = [
        ('read',       '읽기'),
        ('read_write', '읽기/쓰기'),
        ('admin',      '관리자'),
    ]
    file       = models.ForeignKey(File, on_delete=models.CASCADE, null=True, blank=True, verbose_name='파일', related_name='permissions')
    folder     = models.ForeignKey(Folder, on_delete=models.CASCADE, null=True, blank=True, verbose_name='폴더', related_name='permissions')
    user       = models.ForeignKey('accounts.User', on_delete=models.CASCADE, verbose_name='사용자')
    permission = models.CharField('권한', max_length=20, choices=PERM_CHOICES, default='read')

    class Meta:
        db_table = 'nas_file_permissions'
        verbose_name = '파일 권한'


class FileDownloadLog(models.Model):
    file       = models.ForeignKey(File, on_delete=models.CASCADE, verbose_name='파일', related_name='download_logs')
    user       = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, verbose_name='다운로더')
    ip_address = models.GenericIPAddressField('IP주소', null=True, blank=True)
    downloaded_at = models.DateTimeField('다운로드일시', auto_now_add=True)

    class Meta:
        db_table = 'nas_download_logs'
        verbose_name = '다운로드 로그'
