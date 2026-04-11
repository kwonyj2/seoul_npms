"""
gps 앱 모델
GPS 위치 추적, 이동 경로, 지오펜스 관리
"""
from django.db import models


class GpsLog(models.Model):
    """GPS 위치 로그 (주기적 수집)"""
    worker     = models.ForeignKey('accounts.User', on_delete=models.CASCADE, verbose_name='인력', related_name='gps_logs')
    lat        = models.DecimalField('위도', max_digits=10, decimal_places=7)
    lng        = models.DecimalField('경도', max_digits=10, decimal_places=7)
    accuracy   = models.FloatField('정확도(m)', null=True, blank=True)
    speed      = models.FloatField('속도(km/h)', null=True, blank=True)
    heading    = models.FloatField('방향(도)', null=True, blank=True)
    altitude   = models.FloatField('고도(m)', null=True, blank=True)
    device_id   = models.CharField('기기ID', max_length=100, blank=True)
    device_type = models.CharField('단말유형', max_length=10, choices=[('pc','PC'),('mobile','모바일'),('unknown','알수없음')], default='unknown')
    is_moving  = models.BooleanField('이동중', default=False)
    logged_at  = models.DateTimeField('수집일시', db_index=True)

    class Meta:
        db_table = 'gps_logs'
        verbose_name = 'GPS 로그'
        verbose_name_plural = 'GPS 로그 목록'
        ordering = ['-logged_at']
        indexes = [
            models.Index(fields=['worker', 'logged_at']),
        ]

    def __str__(self):
        return f'{self.worker.name} ({self.lat}, {self.lng}) - {self.logged_at}'


class WorkerLocation(models.Model):
    """인력 현재 위치 (최신 1건 유지)"""
    worker      = models.OneToOneField('accounts.User', on_delete=models.CASCADE, verbose_name='인력', related_name='current_location')
    lat         = models.DecimalField('위도', max_digits=10, decimal_places=7)
    lng         = models.DecimalField('경도', max_digits=10, decimal_places=7)
    status      = models.CharField('상태', max_length=30, blank=True)
    device_type = models.CharField('단말유형', max_length=10, choices=[('pc','PC'),('mobile','모바일'),('unknown','알수없음')], default='unknown')
    updated_at  = models.DateTimeField('갱신일시', auto_now=True)

    class Meta:
        db_table = 'worker_locations'
        verbose_name = '인력 현재 위치'

    def __str__(self):
        return f'{self.worker.name} - {self.updated_at}'


class RouteHistory(models.Model):
    """이동 경로 기록"""
    worker     = models.ForeignKey('accounts.User', on_delete=models.CASCADE, verbose_name='인력', related_name='routes')
    incident   = models.ForeignKey('incidents.Incident', on_delete=models.SET_NULL, null=True, blank=True,
                                   verbose_name='관련장애', related_name='routes')
    started_at = models.DateTimeField('출발일시')
    ended_at   = models.DateTimeField('도착일시', null=True, blank=True)
    start_lat  = models.DecimalField('출발위도', max_digits=10, decimal_places=7)
    start_lng  = models.DecimalField('출발경도', max_digits=10, decimal_places=7)
    end_lat    = models.DecimalField('도착위도', max_digits=10, decimal_places=7, null=True, blank=True)
    end_lng    = models.DecimalField('도착경도', max_digits=10, decimal_places=7, null=True, blank=True)
    distance_km= models.DecimalField('이동거리(km)', max_digits=7, decimal_places=2, null=True, blank=True)
    route_points = models.JSONField('경로좌표', default=list, blank=True,
                                    help_text='[{"lat": 37.5, "lng": 127.0, "time": "..."}, ...]')

    class Meta:
        db_table = 'route_history'
        verbose_name = '이동 경로'
        ordering = ['-started_at']


class GeoFence(models.Model):
    """지오펜스 (구역 설정)"""
    FENCE_TYPE_CHOICES = [
        ('support_center', '지원청 담당구역'),
        ('school',         '학교'),
        ('restricted',     '제한구역'),
    ]
    name       = models.CharField('구역명', max_length=100)
    fence_type = models.CharField('구역유형', max_length=20, choices=FENCE_TYPE_CHOICES)
    center_lat = models.DecimalField('중심위도', max_digits=10, decimal_places=7)
    center_lng = models.DecimalField('중심경도', max_digits=10, decimal_places=7)
    radius_m   = models.PositiveIntegerField('반경(m)', default=500)
    is_active  = models.BooleanField('활성', default=True)
    created_at = models.DateTimeField('등록일시', auto_now_add=True)

    class Meta:
        db_table = 'geo_fences'
        verbose_name = '지오펜스'
        verbose_name_plural = '지오펜스 목록'

    def __str__(self):
        return f'{self.name} ({self.radius_m}m)'


class GeoFenceEvent(models.Model):
    """지오펜스 진입/이탈 이벤트"""
    EVENT_CHOICES = [
        ('enter', '진입'),
        ('exit',  '이탈'),
    ]
    worker     = models.ForeignKey('accounts.User', on_delete=models.CASCADE, verbose_name='인력')
    fence      = models.ForeignKey(GeoFence, on_delete=models.CASCADE, verbose_name='지오펜스')
    event_type = models.CharField('이벤트', max_length=10, choices=EVENT_CHOICES)
    lat        = models.DecimalField('위도', max_digits=10, decimal_places=7)
    lng        = models.DecimalField('경도', max_digits=10, decimal_places=7)
    occurred_at= models.DateTimeField('발생일시', auto_now_add=True)

    class Meta:
        db_table = 'geo_fence_events'
        verbose_name = '지오펜스 이벤트'
        ordering = ['-occurred_at']
