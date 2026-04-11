"""
ai_engine 비즈니스 로직
FastAPI AI 서버와의 통신 클라이언트
"""
import httpx
from django.conf import settings
from django.utils import timezone

from .models import AiJob, WorkerAssignmentPrediction

# AI 서버 기본 URL (settings에 없으면 로컬 기본값)
AI_SERVER_URL = getattr(settings, 'AI_SERVER_URL', 'http://npms_ai:8001')
TIMEOUT = 10.0  # seconds


def _ai_post(path: str, payload: dict) -> dict:
    """AI 서버 POST 요청 공통 처리"""
    url = f"{AI_SERVER_URL}{path}"
    with httpx.Client(timeout=TIMEOUT) as client:
        resp = client.post(url, json=payload)
        resp.raise_for_status()
        return resp.json()


# ── 인력 자동 배정 ────────────────────────────────────────────

def predict_worker_assignment(incident, workers_qs) -> list:
    """
    incident: Incident 모델 인스턴스
    workers_qs: 후보 User 쿼리셋 (lat/lng 필드 있어야 함)
    반환: AssignmentResult 딕셔너리 리스트 (점수 내림차순 상위 3)
    """
    job = AiJob.objects.create(
        job_type='worker_assignment',
        status='running',
        started_at=timezone.now(),
    )

    try:
        worker_list = []
        for w in workers_qs:
            worker_list.append({
                "worker_id":        w.pk,
                "worker_name":      w.get_full_name() or w.username,
                "lat":              getattr(w, 'lat', None),
                "lng":              getattr(w, 'lng', None),
                "current_workload": getattr(w, 'current_workload', 0),
                "skills":           [],
            })

        payload = {
            "incident": {
                "incident_id":  incident.pk,
                "lat":          float(incident.lat) if hasattr(incident, 'lat') and incident.lat else 0,
                "lng":          float(incident.lng) if hasattr(incident, 'lng') and incident.lng else 0,
                "incident_type": str(incident.category) if hasattr(incident, 'category') else None,
                "urgency":      incident.urgency if hasattr(incident, 'urgency') else "normal",
                "school_id":    incident.school_id if hasattr(incident, 'school_id') else None,
            },
            "workers": worker_list,
        }

        result = _ai_post('/predict/worker_assignment', payload)

        # 예측 결과 DB 저장 (1위)
        if result:
            top = result[0]
            WorkerAssignmentPrediction.objects.create(
                incident=incident,
                recommended_worker_id=top['worker_id'],
                distance_km=top.get('distance_km'),
                eta_minutes=top.get('eta_minutes'),
                score=top.get('score', 0.0),
                reason=top.get('reason', ''),
            )

        job.output_data = result
        job.status = 'success'
        job.finished_at = timezone.now()
        job.save(update_fields=['output_data', 'status', 'finished_at'])
        return result

    except Exception as exc:
        job.status = 'failed'
        job.error_msg = str(exc)
        job.finished_at = timezone.now()
        job.save(update_fields=['status', 'error_msg', 'finished_at'])
        raise


# ── 자재 수요 예측 ────────────────────────────────────────────

def forecast_material(material_id: int, usage_history: list,
                      forecast_periods: int = 4, window: int = 4,
                      material_name: str = None) -> dict:
    """
    usage_history: [{"period": "2024-W01", "quantity": 10.0}, ...]
    반환: ForecastResult 딕셔너리
    """
    job = AiJob.objects.create(
        job_type='material_forecast',
        status='running',
        started_at=timezone.now(),
    )

    try:
        payload = {
            "material_id":      material_id,
            "material_name":    material_name,
            "usage_history":    usage_history,
            "forecast_periods": forecast_periods,
            "window":           window,
        }

        result = _ai_post('/predict/material_forecast', payload)

        job.output_data = result
        job.status = 'success'
        job.finished_at = timezone.now()
        job.save(update_fields=['output_data', 'status', 'finished_at'])
        return result

    except Exception as exc:
        job.status = 'failed'
        job.error_msg = str(exc)
        job.finished_at = timezone.now()
        job.save(update_fields=['status', 'error_msg', 'finished_at'])
        raise


# ── 장애 패턴 분석 ────────────────────────────────────────────

def analyze_incident_patterns(incidents_qs, top_n: int = 5) -> dict:
    """
    incidents_qs: Incident 쿼리셋
    반환: PatternResult 딕셔너리
    """
    job = AiJob.objects.create(
        job_type='incident_pattern',
        status='running',
        started_at=timezone.now(),
    )

    try:
        records = []
        for inc in incidents_qs.select_related('school', 'category'):
            records.append({
                "incident_id":   inc.pk,
                "school_id":     inc.school_id,
                "school_name":   inc.school.school_name if inc.school else None,
                "incident_type": str(inc.category) if inc.category else None,
                "occurred_at":   inc.occurred_at.isoformat() if hasattr(inc, 'occurred_at') and inc.occurred_at else inc.created_at.isoformat(),
                "resolved_at":   inc.resolved_at.isoformat() if hasattr(inc, 'resolved_at') and inc.resolved_at else None,
                "status":        inc.status,
            })

        payload = {"incidents": records, "top_n": top_n}
        result = _ai_post('/analyze/incident_pattern', payload)

        job.output_data = result
        job.status = 'success'
        job.finished_at = timezone.now()
        job.save(update_fields=['output_data', 'status', 'finished_at'])
        return result

    except Exception as exc:
        job.status = 'failed'
        job.error_msg = str(exc)
        job.finished_at = timezone.now()
        job.save(update_fields=['status', 'error_msg', 'finished_at'])
        raise


# ── 헬스체크 ──────────────────────────────────────────────────

def ai_server_health() -> dict:
    """AI 서버 상태 확인"""
    try:
        with httpx.Client(timeout=3.0) as client:
            resp = client.get(f"{AI_SERVER_URL}/health")
            resp.raise_for_status()
            return {"online": True, **resp.json()}
    except Exception as exc:
        return {"online": False, "error": str(exc)}
