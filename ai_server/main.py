"""
NPMS AI Server - FastAPI
인력 자동 배정 / 자재 수요 예측 / 장애 패턴 분석
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import worker_assignment, material_forecast, incident_pattern, classify

app = FastAPI(
    title="NPMS AI Server",
    description="서울시교육청 NPMS 인공지능 추론 서버",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(worker_assignment.router, prefix="/predict",  tags=["인력 배정"])
app.include_router(material_forecast.router, prefix="/predict",  tags=["자재 예측"])
app.include_router(incident_pattern.router,  prefix="/analyze",  tags=["장애 패턴"])
app.include_router(classify.router,          prefix="/api/classify", tags=["AI 분류"])


@app.get("/health")
def health():
    return {"status": "ok", "service": "NPMS AI Server"}


@app.get("/models")
def list_models():
    """사용 가능한 AI 모델 목록"""
    return {
        "models": [
            {"name": "worker_assignment", "type": "rule+distance", "version": "1.0"},
            {"name": "material_forecast", "type": "moving_average", "version": "1.0"},
            {"name": "incident_pattern",  "type": "frequency_analysis", "version": "1.0"},
        ]
    }
