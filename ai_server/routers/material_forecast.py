"""
자재 수요 예측 API
이동평균 + 계절성 보정으로 다음 N주 소모량 예측
"""
from typing import List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import statistics

router = APIRouter()


class UsageRecord(BaseModel):
    period:   str        # "2024-W01" 또는 "2024-01"
    quantity: float


class ForecastRequest(BaseModel):
    material_id:     int
    material_name:   Optional[str] = None
    usage_history:   List[UsageRecord]   # 최근 이력 (오래된 것 → 최신)
    forecast_periods: int = 4            # 예측할 기간 수 (기본 4주)
    window:           int = 4            # 이동평균 윈도우 크기


class ForecastResult(BaseModel):
    material_id:   int
    material_name: Optional[str]
    forecasts:     List[dict]            # {period, predicted_qty, lower, upper}
    trend:         str                   # "increasing" | "stable" | "decreasing"
    avg_weekly:    float
    recommendation: str


def moving_average(values: List[float], window: int) -> float:
    if len(values) < window:
        return statistics.mean(values) if values else 0.0
    return statistics.mean(values[-window:])


def linear_trend(values: List[float]) -> float:
    """기울기 (양수=증가, 음수=감소)"""
    n = len(values)
    if n < 2: return 0.0
    x_mean = (n - 1) / 2
    y_mean = statistics.mean(values)
    num = sum((i - x_mean) * (values[i] - y_mean) for i in range(n))
    den = sum((i - x_mean) ** 2 for i in range(n))
    return num / den if den else 0.0


@router.post("/material_forecast", response_model=ForecastResult)
def forecast_material(req: ForecastRequest):
    """
    이동평균 기반 자재 수요 예측
    """
    if len(req.usage_history) < 2:
        raise HTTPException(status_code=400, detail="최소 2개 이상의 이력이 필요합니다.")

    values = [r.quantity for r in req.usage_history]
    window = min(req.window, len(values))
    base_avg = moving_average(values, window)
    slope    = linear_trend(values)

    # 표준편차로 신뢰구간 계산
    std = statistics.stdev(values) if len(values) >= 2 else base_avg * 0.2

    forecasts = []
    last_period = req.usage_history[-1].period
    for i in range(1, req.forecast_periods + 1):
        # 트렌드 반영: 매 기간마다 slope만큼 증가/감소
        predicted = max(0.0, base_avg + slope * i)
        lower = max(0.0, predicted - std * 1.5)
        upper = predicted + std * 1.5
        forecasts.append({
            "period":        f"{last_period}+{i}",
            "predicted_qty": round(predicted, 1),
            "lower":         round(lower, 1),
            "upper":         round(upper, 1),
        })

    # 트렌드 판정
    if slope > base_avg * 0.05:       trend = "increasing"
    elif slope < -base_avg * 0.05:    trend = "decreasing"
    else:                              trend = "stable"

    # 발주 권고
    next_4w = sum(f["predicted_qty"] for f in forecasts[:4])
    if trend == "increasing":
        recommendation = f"향후 4기간 예상 소모량: {next_4w:.0f}개. 수요 증가 추세로 재고 확충 권장."
    elif trend == "decreasing":
        recommendation = f"향후 4기간 예상 소모량: {next_4w:.0f}개. 수요 감소 추세로 최소 발주 권장."
    else:
        recommendation = f"향후 4기간 예상 소모량: {next_4w:.0f}개. 안정적 수요로 정기 발주 유지."

    return ForecastResult(
        material_id=req.material_id,
        material_name=req.material_name,
        forecasts=forecasts,
        trend=trend,
        avg_weekly=round(base_avg, 2),
        recommendation=recommendation,
    )


@router.post("/material_forecast/batch")
def batch_forecast(requests: List[ForecastRequest]):
    """여러 자재 일괄 예측"""
    results = []
    for req in requests:
        try:
            results.append(forecast_material(req).model_dump())
        except Exception as e:
            results.append({"material_id": req.material_id, "error": str(e)})
    return results
