#!/bin/bash
# NPMS 롤백 스크립트
# 사용법: ./infra/rollback.sh [tag/commit]
set -e

PROJECT_DIR="/home/kwonyj/network_pms"
CONTAINER="npms_web"

TARGET="${1:-HEAD~1}"

echo "=== NPMS 롤백 시작 → ${TARGET} $(date) ==="

cd "$PROJECT_DIR"

# 현재 상태 백업
CURRENT=$(git rev-parse --short HEAD)
echo "현재 커밋: $CURRENT"

# 롤백 (git reset 또는 git checkout)
echo "[1/4] 소스 롤백..."
git reset --hard "$TARGET"
echo "롤백 완료: $(git rev-parse --short HEAD)"

# 마이그레이션 (필요시 이전 버전으로)
echo "[2/4] DB 마이그레이션 상태 확인..."
docker exec "$CONTAINER" python manage.py migrate --noinput

# 정적 파일
echo "[3/4] 정적 파일 재수집..."
docker exec "$CONTAINER" python manage.py collectstatic --noinput

# 재시작
echo "[4/4] 컨테이너 재시작..."
docker compose restart npms_web

echo "=== 롤백 완료 $(date) ==="
echo "현재 HEAD: $(git log --oneline -1)"
