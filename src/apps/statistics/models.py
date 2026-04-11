"""
statistics 앱 모델
일별/월별/연별 통계, SLA, 성능 지표
"""
from django.db import models


class StatisticsDaily(models.Model):
    """일별 통계"""
    stat_date         = models.DateField('통계일', unique=True, db_index=True)
    total_incidents   = models.PositiveIntegerField('총 장애수', default=0)
    completed_incidents = models.PositiveIntegerField('완료 장애수', default=0)
    sla_arrival_ok    = models.PositiveIntegerField('SLA도착준수', default=0)
    sla_resolve_ok    = models.PositiveIntegerField('SLA처리준수', default=0)
    avg_arrival_min   = models.FloatField('평균도착시간(분)', null=True, blank=True)
    avg_resolve_min   = models.FloatField('평균처리시간(분)', null=True, blank=True)
    active_workers    = models.PositiveSmallIntegerField('활동인력수', default=0)
    created_at        = models.DateTimeField('생성일시', auto_now_add=True)
    updated_at        = models.DateTimeField('수정일시', auto_now=True)

    class Meta:
        db_table = 'statistics_daily'
        verbose_name = '일별 통계'
        ordering = ['-stat_date']

    def __str__(self):
        return str(self.stat_date)


class StatisticsMonthly(models.Model):
    """월별 통계"""
    year              = models.PositiveSmallIntegerField('연도')
    month             = models.PositiveSmallIntegerField('월')
    support_center    = models.ForeignKey('schools.SupportCenter', on_delete=models.CASCADE, null=True, blank=True, verbose_name='지원청')
    total_incidents   = models.PositiveIntegerField('총 장애수', default=0)
    completed_incidents = models.PositiveIntegerField('완료 장애수', default=0)
    sla_arrival_rate  = models.FloatField('SLA도착준수율(%)', default=0.0)
    sla_resolve_rate  = models.FloatField('SLA처리준수율(%)', default=0.0)
    avg_arrival_min   = models.FloatField('평균도착시간(분)', null=True, blank=True)
    avg_resolve_min   = models.FloatField('평균처리시간(분)', null=True, blank=True)
    avg_satisfaction  = models.FloatField('평균만족도', null=True, blank=True)
    created_at        = models.DateTimeField('생성일시', auto_now_add=True)

    class Meta:
        db_table = 'statistics_monthly'
        verbose_name = '월별 통계'
        unique_together = [['year', 'month', 'support_center']]
        ordering = ['-year', '-month']


class SLARecord(models.Model):
    """SLA 측정 상세 기록"""
    incident      = models.OneToOneField('incidents.Incident', on_delete=models.CASCADE, verbose_name='장애', related_name='sla_record')
    sla_rule      = models.ForeignKey('incidents.SLARule', on_delete=models.SET_NULL, null=True, verbose_name='적용 SLA 기준')
    arrival_target_min = models.PositiveIntegerField('도착기준(분)')
    resolve_target_min = models.PositiveIntegerField('처리기준(분)')
    arrival_actual_min = models.IntegerField('실제도착(분)', null=True, blank=True)
    resolve_actual_min = models.IntegerField('실제처리(분)', null=True, blank=True)
    arrival_ok    = models.BooleanField('도착준수', null=True)
    resolve_ok    = models.BooleanField('처리준수', null=True)
    created_at    = models.DateTimeField('생성일시', auto_now_add=True)

    class Meta:
        db_table = 'sla_records'
        verbose_name = 'SLA 기록'


class SatisfactionSurvey(models.Model):
    """서비스 만족도 조사"""
    STATUS_CHOICES = [
        ('sent',      '발송완료'),
        ('responded', '응답완료'),
        ('expired',   '만료'),
    ]
    incident    = models.OneToOneField('incidents.Incident', on_delete=models.CASCADE, verbose_name='장애', related_name='satisfaction')
    sent_to     = models.CharField('발송대상 연락처', max_length=20)
    sent_at     = models.DateTimeField('발송일시', auto_now_add=True)
    status      = models.CharField('상태', max_length=10, choices=STATUS_CHOICES, default='sent')
    score       = models.PositiveSmallIntegerField('만족도(1-5)', null=True, blank=True)
    comment     = models.TextField('의견', blank=True)
    responded_at= models.DateTimeField('응답일시', null=True, blank=True)
    token       = models.CharField('응답토큰', max_length=100, unique=True)

    class Meta:
        db_table = 'satisfaction_surveys'
        verbose_name = '만족도 조사'


class PerformanceMetric(models.Model):
    """시스템 성능 지표"""
    metric_name  = models.CharField('지표명', max_length=100)
    metric_value = models.FloatField('값')
    unit         = models.CharField('단위', max_length=20, blank=True)
    collected_at = models.DateTimeField('수집일시', auto_now_add=True)

    class Meta:
        db_table = 'performance_metrics'
        verbose_name = '성능 지표'
        ordering = ['-collected_at']
