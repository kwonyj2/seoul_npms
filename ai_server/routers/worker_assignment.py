"""
인력 자동 배정 추론 API
입력: 장애 위치(lat, lng), 장애 유형, 긴급도
출력: 추천 기사 목록 (거리, ETA, 점수 포함)
"""
import math
from typing import Optional, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


class IncidentInfo(BaseModel):
    incident_id:  int
    lat:          float
    lng:          float
    incident_type: Optional[str] = None
    urgency:      Optional[str] = "normal"   # low | normal | high | critical
    school_id:    Optional[int] = None


class WorkerCandidate(BaseModel):
    worker_id:   int
    worker_name: str
    lat:         Optional[float] = None
    lng:         Optional[float] = None
    current_workload: int = 0          # 현재 처리 중인 장애 수
    skills:      Optional[List[str]] = []


class AssignmentRequest(BaseModel):
    incident:  IncidentInfo
    workers:   List[WorkerCandidate]


class AssignmentResult(BaseModel):
    worker_id:    int
    worker_name:  str
    distance_km:  float
    eta_minutes:  int
    score:        float
    reason:       str


def haversine(lat1, lng1, lat2, lng2) -> float:
    """두 좌표 사이의 직선 거리(km)"""
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat/2)**2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng/2)**2)
    return 2 * R * math.asin(math.sqrt(a))


def compute_score(distance_km: float, workload: int, urgency: str) -> float:
    """배정 점수 계산 (높을수록 좋음)
    - 거리가 가까울수록 높은 점수
    - 현재 업무량이 적을수록 높은 점수
    - 긴급도에 따라 거리 가중치 조정
    """
    urgency_weight = {"low": 0.5, "normal": 1.0, "high": 1.5, "critical": 2.0}
    w = urgency_weight.get(urgency, 1.0)

    # 거리 점수: 50km 기준, 가까울수록 1.0 → 0
    dist_score = max(0.0, 1.0 - (distance_km / 50.0) * w)

    # 업무량 페널티: 장애 1건당 0.15 감점
    workload_penalty = min(0.6, workload * 0.15)

    return round(max(0.0, dist_score - workload_penalty), 3)


@router.post("/worker_assignment", response_model=List[AssignmentResult])
def predict_worker_assignment(req: AssignmentRequest):
    """
    인력 자동 배정 추천
    - 거리 + 업무량 + 긴급도 기반 점수 산출
    - 상위 3명 반환 (점수 내림차순)
    """
    if not req.workers:
        raise HTTPException(status_code=400, detail="추천 대상 기사가 없습니다.")

    incident = req.incident
    results  = []

    for w in req.workers:
        if w.lat is None or w.lng is None:
            # 위치 정보 없으면 30km 가정
            dist_km = 30.0
        else:
            dist_km = haversine(incident.lat, incident.lng, w.lat, w.lng)

        # 이동속도 30km/h 기준 ETA 계산
        eta_min = int(dist_km / 30.0 * 60)

        score = compute_score(dist_km, w.current_workload, incident.urgency or "normal")

        reasons = []
        if dist_km < 5:   reasons.append(f"근거리({dist_km:.1f}km)")
        elif dist_km < 15: reasons.append(f"중거리({dist_km:.1f}km)")
        else:              reasons.append(f"원거리({dist_km:.1f}km)")
        if w.current_workload == 0: reasons.append("여유 있음")
        elif w.current_workload >= 3: reasons.append("업무 과중")

        results.append(AssignmentResult(
            worker_id=w.worker_id,
            worker_name=w.worker_name,
            distance_km=round(dist_km, 2),
            eta_minutes=eta_min,
            score=score,
            reason=" | ".join(reasons),
        ))

    # 점수 내림차순 정렬 후 상위 3명
    results.sort(key=lambda x: x.score, reverse=True)
    return results[:3]


@router.post("/worker_assignment/batch", response_model=List[dict])
def batch_assign(incidents: List[IncidentInfo], workers: List[WorkerCandidate]):
    """여러 장애를 한 번에 배정 최적화 (간소화 버전)"""
    results = []
    for incident in incidents:
        req = AssignmentRequest(incident=incident, workers=workers)
        try:
            top = predict_worker_assignment(req)
            results.append({
                "incident_id": incident.incident_id,
                "recommended": top[0].model_dump() if top else None,
                "alternatives": [r.model_dump() for r in top[1:]] if len(top) > 1 else [],
            })
        except Exception as e:
            results.append({"incident_id": incident.incident_id, "error": str(e)})
    return results
