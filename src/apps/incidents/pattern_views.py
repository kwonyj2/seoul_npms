"""
장애 패턴 분석 API 뷰
"""
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.utils import timezone

from apps.schools.models import SupportCenter
from .pattern_service import (
    predict_vulnerable_assets,
    analyze_seasonal_pattern,
    analyze_hourly_pattern,
    predict_sla_risk,
    generate_monthly_insight,
)
from .models import Incident


def _get_center(request):
    """쿼리 파라미터 center에서 SupportCenter 반환. 없으면 None."""
    center_id = request.query_params.get('center')
    if center_id:
        try:
            return SupportCenter.objects.get(pk=center_id)
        except SupportCenter.DoesNotExist:
            return None
    return None


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def vulnerable_assets_api(request):
    """학교별 취약 장비 예측

    Query params:
        center (int): 지원청 PK (필수)
        top_n  (int): 반환 건수 (기본 20)
    """
    center = _get_center(request)
    if not center:
        return Response({'error': 'center 파라미터(지원청 PK)가 필요합니다.'}, status=400)

    top_n = int(request.query_params.get('top_n', 20))
    results = predict_vulnerable_assets(center=center, top_n=top_n)
    return Response({'results': results, 'center': center.name})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def seasonal_pattern_api(request):
    """계절별 장애 패턴 분석 (5분 캐시)

    Query params:
        center (int): 지원청 PK (선택 — 없으면 전체)
        year   (int): 연도 필터 (선택)
    """
    from django.core.cache import cache
    center = _get_center(request)
    year = request.query_params.get('year', '')
    center_id = center.pk if center else 0
    cache_key = f'pattern_seasonal_{center_id}_{year}'
    cached = cache.get(cache_key)
    if cached is not None:
        return Response(cached)

    qs = Incident.objects.all()
    if center:
        qs = qs.filter(school__support_center=center)
    if year:
        qs = qs.filter(received_at__year=year)

    hourly = analyze_hourly_pattern(qs)
    seasons = analyze_seasonal_pattern(qs)
    data = {
        'seasons': seasons,
        'hourly':  hourly,
        'center':  center.name if center else '전체',
    }
    cache.set(cache_key, data, 300)
    return Response(data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def sla_risk_api(request):
    """SLA 위반 예측 (미완료 장애 위험도)

    Query params:
        center    (int):   지원청 PK (필수)
        threshold (float): 최소 위험도 % (기본 0 = 전체)
    """
    center = _get_center(request)
    if not center:
        return Response({'error': 'center 파라미터(지원청 PK)가 필요합니다.'}, status=400)

    threshold = float(request.query_params.get('threshold', 0))
    results = predict_sla_risk(center=center, threshold=threshold)
    return Response({
        'results':   results,
        'center':    center.name,
        'generated': timezone.now().strftime('%Y-%m-%d %H:%M:%S'),
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def monthly_insight_api(request):
    """월간 인사이트 리포트 자동 생성 (5분 캐시)

    Query params:
        center (int): 지원청 PK (필수)
        year   (int): 연도 (기본 올해)
        month  (int): 월 (기본 이번 달)
    """
    from django.core.cache import cache
    center = _get_center(request)
    if not center:
        return Response({'error': 'center 파라미터(지원청 PK)가 필요합니다.'}, status=400)

    now = timezone.now()
    year = int(request.query_params.get('year', now.year))
    month = int(request.query_params.get('month', now.month))

    cache_key = f'pattern_monthly_insight_{center.pk}_{year}_{month}'
    cached = cache.get(cache_key)
    if cached is not None:
        return Response(cached)

    report = generate_monthly_insight(center=center, year=year, month=month)
    cache.set(cache_key, report, 300)
    return Response(report)
