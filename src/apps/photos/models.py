"""
photos 앱 모델
현장 작업 사진 관리 (GPS, NAS 자동 저장)
"""
from django.db import models


class PhotoWorkType(models.Model):
    """작업명 (관리자 설정 가능)"""
    name      = models.CharField('작업명', max_length=100, unique=True)
    order     = models.PositiveSmallIntegerField('정렬순서', default=0)
    is_active = models.BooleanField('활성', default=True)

    class Meta:
        db_table = 'photo_work_types'
        verbose_name = '작업 유형'
        ordering = ['order']

    def __str__(self):
        return self.name


def photo_upload_path(instance, filename):
    """보고서 타입에 따라 저장 경로 분기"""
    if instance.report_type == 'cable':
        return f'산출물/소규모케이블 이미지/{filename}'
    elif instance.report_type == 'switch_install':
        return f'산출물/스위치설치/{filename}'
    return f'photos/{filename}'


class Photo(models.Model):
    """현장 작업 사진"""
    PHOTO_STAGE_CHOICES = [
        ('before', '작업전'),
        ('after',  '작업후'),
        ('other',  '기타'),
    ]
    BUILDING_CHOICES = [
        ('main',  '본관'),
        ('annex', '별관'),
        ('east',  '동관'),
        ('west',  '서관'),
        ('other', '기타'),
    ]

    school      = models.ForeignKey('schools.School', on_delete=models.CASCADE, verbose_name='학교', related_name='photos')
    building    = models.ForeignKey('schools.SchoolBuilding', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='건물')
    floor       = models.ForeignKey('schools.SchoolFloor', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='층')
    room        = models.ForeignKey('schools.SchoolRoom', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='교실')
    # 텍스트 기반 위치 (스위치 DB 연동)
    building_name = models.CharField('건물명', max_length=100, blank=True)
    floor_name    = models.CharField('층', max_length=50, blank=True)
    room_name     = models.CharField('설치장소', max_length=100, blank=True)

    work_type   = models.ForeignKey(PhotoWorkType, on_delete=models.SET_NULL, null=True, verbose_name='작업명')
    work_type_etc = models.CharField('작업명(기타)', max_length=100, blank=True)
    photo_stage = models.CharField('단계', max_length=10, choices=PHOTO_STAGE_CHOICES, default='other')

    # 보고서 타입 (저장 경로 분기용)
    report_type = models.CharField('보고서유형', max_length=30, blank=True,
                                    help_text='cable, switch_install 등 — 저장 경로 결정')

    # 파일
    image       = models.ImageField('이미지', upload_to=photo_upload_path)
    nas_path    = models.CharField('NAS 저장경로', max_length=500, blank=True)
    file_name   = models.CharField('파일명', max_length=255, blank=True,
                                    help_text='학교명_건물_층_교실명_작업명_단계_날짜+NO.jpg')
    file_size   = models.BigIntegerField('파일크기(bytes)', default=0)

    # GPS
    gps_lat     = models.DecimalField('촬영위도', max_digits=10, decimal_places=7, null=True, blank=True)
    gps_lng     = models.DecimalField('촬영경도', max_digits=10, decimal_places=7, null=True, blank=True)
    gps_accuracy= models.FloatField('GPS정확도(m)', null=True, blank=True)

    # AI 분류
    ai_category = models.CharField('AI분류결과', max_length=50, blank=True)
    ai_confidence = models.FloatField('AI신뢰도', null=True, blank=True)

    # 미디어 최적화 — 리사이즈 WebP + 썸네일
    thumbnail   = models.ImageField('썸네일(200px)', upload_to='photos/thumbs/',
                                    null=True, blank=True)

    # AI 품질 검사 / 불량 감지
    quality_score  = models.FloatField('품질점수', null=True, blank=True)
    is_blurry      = models.BooleanField('흔들림여부', default=False)
    is_dark        = models.BooleanField('어두움여부', default=False)
    defect_flags   = models.JSONField('불량플래그', default=dict)
    needs_retake   = models.BooleanField('재촬영필요', default=False)
    retake_reason  = models.CharField('재촬영사유', max_length=200, blank=True)
    ai_stage       = models.CharField('AI단계분류', max_length=10, blank=True)

    # 연결
    incident    = models.ForeignKey('incidents.Incident', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='관련장애')
    taken_by    = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, verbose_name='촬영자')
    taken_at    = models.DateTimeField('촬영일시')
    uploaded_at = models.DateTimeField('업로드일시', auto_now_add=True)

    # 휴지통
    is_deleted  = models.BooleanField('삭제여부', default=False)
    deleted_at  = models.DateTimeField('삭제일시', null=True, blank=True)

    class Meta:
        db_table = 'photos'
        verbose_name = '작업 사진'
        verbose_name_plural = '작업 사진 목록'
        ordering = ['-taken_at']
        indexes = [
            models.Index(fields=['school', 'taken_at']),
        ]

    def __str__(self):
        return self.file_name or f'{self.school.name} - {self.taken_at}'
