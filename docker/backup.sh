#!/bin/bash
# NPMS PostgreSQL 자동 백업
# 사용법: ./backup.sh
# Cron 예시: 0 2 * * * /home/kwonyj/network_pms/docker/backup.sh >> /var/log/npms_backup.log 2>&1

set -euo pipefail

BACKUP_DIR="/home/kwonyj/network_pms/backups"
KEEP_DAYS=30
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/npms_db_${DATE}.sql.gz"

# .env 로드
ENV_FILE="/home/kwonyj/network_pms/.env"
if [ -f "$ENV_FILE" ]; then
    export $(grep -v '^#' "$ENV_FILE" | grep -E '^(DB_NAME|DB_USER|DB_PASSWORD)=' | xargs)
fi

DB_NAME="${DB_NAME:-npms_db}"
DB_USER="${DB_USER:-django}"
DB_PASSWORD="${DB_PASSWORD:-django_password}"

mkdir -p "$BACKUP_DIR"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] 백업 시작: $BACKUP_FILE"

# Docker 컨테이너 내부에서 pg_dump 실행
docker exec -e PGPASSWORD="$DB_PASSWORD" npms_db \
    pg_dump -U "$DB_USER" -d "$DB_NAME" --no-password \
    | gzip > "$BACKUP_FILE"

SIZE=$(du -sh "$BACKUP_FILE" | cut -f1)
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 백업 완료: $BACKUP_FILE ($SIZE)"

# 오래된 백업 삭제
DELETED=$(find "$BACKUP_DIR" -name "npms_db_*.sql.gz" -mtime +${KEEP_DAYS} -print -delete | wc -l)
if [ "$DELETED" -gt 0 ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 구 백업 ${DELETED}개 삭제 (${KEEP_DAYS}일 이상)"
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] 완료"
