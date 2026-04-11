#!/bin/bash
# NPMS 배포 스크립트
# 사용법: ./infra/deploy.sh [--skip-tests]
set -e

PROJECT_DIR="/home/kwonyj/network_pms"
CONTAINER="npms_web"

echo "=== NPMS 배포 시작 $(date) ==="

cd "$PROJECT_DIR"

# 1. 소스 업데이트
echo "[1/6] 소스 업데이트..."
git pull origin main

# 2. 테스트 실행 (--skip-tests 옵션 없을 때만)
if [[ "$1" != "--skip-tests" ]]; then
    echo "[2/6] 테스트 실행..."
    docker exec "$CONTAINER" python manage.py test --verbosity=1
    echo "테스트 통과 ✓"
else
    echo "[2/6] 테스트 건너뜀 (--skip-tests)"
fi

# 3. 마이그레이션
echo "[3/6] DB 마이그레이션..."
docker exec "$CONTAINER" python manage.py migrate --noinput

# 4. 정적 파일 수집
echo "[4/6] 정적 파일 collectstatic..."
docker exec "$CONTAINER" python manage.py collectstatic --noinput

# 5. 컨테이너 재시작
echo "[5/6] 웹 컨테이너 재시작..."
docker compose restart npms_web

# 6. 배포 완료 알림 SMS
echo "[6/6] 배포 완료 SMS 알림..."
docker exec "$CONTAINER" python manage.py shell -c \
    "from core.tasks import notify_deploy_complete; notify_deploy_complete.delay()" \
    2>/dev/null || echo "SMS 알림 전송 실패 (무시)"

echo "=== 배포 완료 $(date) ==="
