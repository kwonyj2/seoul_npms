"""
ai_engine 앱 모델
AI 예측, 배정, 이미지 분류, 문서 분류
"""
from django.db import models


class AiModel(models.Model):
    """등록된 AI 모델"""
    MODEL_TYPE_CHOICES = [
        ('worker_assignment', '인력 자동 배정'),
        ('material_forecast', '자재 수요 예측'),
        ('image_classifier',  '이미지 분류(YOLO)'),
        ('doc_classifier',    '문서 분류'),
        ('incident_pattern',  '장애 패턴 분석'),
    ]
    name       = models.CharField('모델명', max_length=100)
    model_type = models.CharField('유형', max_length=30, choices=MODEL_TYPE_CHOICES)
    version    = models.CharField('버전', max_length=20)
    endpoint   = models.CharField('API 엔드포인트', max_length=200, blank=True)
    is_active  = models.BooleanField('활성', default=True)
    created_at = models.DateTimeField('등록일시', auto_now_add=True)

    class Meta:
        db_table = 'ai_models'
        verbose_name = 'AI 모델'

    def __str__(self):
        return f'{self.name} v{self.version}'


class AiJob(models.Model):
    """AI 작업 실행 이력"""
    STATUS_CHOICES = [
        ('pending',  '대기'),
        ('running',  '실행중'),
        ('success',  '성공'),
        ('failed',   '실패'),
    ]
    ai_model    = models.ForeignKey(AiModel, on_delete=models.SET_NULL, null=True, verbose_name='AI모델')
    job_type    = models.CharField('작업유형', max_length=30)
    input_data  = models.JSONField('입력 데이터', default=dict)
    output_data = models.JSONField('출력 데이터', default=dict)
    status      = models.CharField('상태', max_length=10, choices=STATUS_CHOICES, default='pending')
    error_msg   = models.TextField('오류메시지', blank=True)
    started_at  = models.DateTimeField('시작일시', null=True, blank=True)
    finished_at = models.DateTimeField('완료일시', null=True, blank=True)
    created_at  = models.DateTimeField('등록일시', auto_now_add=True)

    class Meta:
        db_table = 'ai_jobs'
        verbose_name = 'AI 작업'
        ordering = ['-created_at']


class WorkerAssignmentPrediction(models.Model):
    """인력 자동 배정 예측 결과"""
    incident      = models.ForeignKey('incidents.Incident', on_delete=models.CASCADE, verbose_name='장애', related_name='ai_predictions')
    recommended_worker = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, verbose_name='추천 인력')
    distance_km   = models.DecimalField('거리(km)', max_digits=6, decimal_places=2, null=True, blank=True)
    eta_minutes   = models.PositiveIntegerField('예상도착(분)', null=True, blank=True)
    score         = models.FloatField('적합도 점수', default=0.0)
    reason        = models.TextField('추천 이유', blank=True)
    is_accepted   = models.BooleanField('채택여부', null=True)
    created_at    = models.DateTimeField('예측일시', auto_now_add=True)

    class Meta:
        db_table = 'worker_assignment_predictions'
        verbose_name = '인력 배정 예측'
        ordering = ['-score']


class IncidentPattern(models.Model):
    """장애 패턴 분석"""
    school       = models.ForeignKey('schools.School', on_delete=models.CASCADE, verbose_name='학교', null=True, blank=True)
    category     = models.ForeignKey('incidents.IncidentCategory', on_delete=models.SET_NULL, null=True, verbose_name='분류')
    pattern_type = models.CharField('패턴유형', max_length=100)
    description  = models.TextField('패턴설명')
    frequency    = models.PositiveIntegerField('발생빈도', default=0)
    avg_resolve_min = models.IntegerField('평균처리시간(분)', null=True, blank=True)
    analyzed_at  = models.DateTimeField('분석일시', auto_now_add=True)

    class Meta:
        db_table = 'incident_patterns'
        verbose_name = '장애 패턴'
        ordering = ['-frequency']


class ImageClassification(models.Model):
    """이미지 AI 분류 결과"""
    photo        = models.OneToOneField('photos.Photo', on_delete=models.CASCADE, verbose_name='사진', related_name='ai_classification')
    predicted_class = models.CharField('예측 분류', max_length=100)
    confidence   = models.FloatField('신뢰도')
    all_scores   = models.JSONField('전체 점수', default=dict)
    model_version= models.CharField('모델버전', max_length=20, blank=True)
    classified_at= models.DateTimeField('분류일시', auto_now_add=True)

    class Meta:
        db_table = 'image_classifications'
        verbose_name = '이미지 분류'
