#!/bin/bash
# ═══════════════════════════════════════════════════════════
# NPMS 전체 백업 스크립트
# 소스코드 + DB + .env + SSL + SSH + nginx 설정을 암호화 백업
# 실행: sudo /home/pms/seoul_npms/scripts/npms_full_backup.sh
# 복구: gpg -d 파일.gpg > 파일.tar.gz && tar xzf 파일.tar.gz
# ═══════════════════════════════════════════════════════════

set -e

# ── 설정 ──────────────────────────────────────────────────
BACKUP_DIR="/mnt/lvm-cache/backup"
APP_DIR="/home/pms/seoul_npms"
DATE=$(date +%Y%m%d_%H%M)
BACKUP_NAME="npms_full_${DATE}"
TEMP_DIR="${BACKUP_DIR}/.tmp_${BACKUP_NAME}"
PASSPHRASE="***npmsadmin@"
KEEP_DAYS=30

echo "======================================"
echo "  NPMS 전체 백업 시작: $(date)"
echo "======================================"

# ── 임시 디렉토리 ────────────────────────────────────────
mkdir -p "${TEMP_DIR}"

# ── 1. 소스코드 ──────────────────────────────────────────
echo "[1/7] 소스코드 백업..."
tar czf "${TEMP_DIR}/source.tar.gz" \
    -C /home/pms seoul_npms \
    --exclude='seoul_npms/.git' \
    --exclude='seoul_npms/__pycache__' \
    --exclude='seoul_npms/src/__pycache__' \
    --exclude='seoul_npms/src/.preview_cache' \
    --exclude='*.pyc' \
    2>/dev/null || true
echo "      소스코드 완료"

# ── 2. DB 덤프 ───────────────────────────────────────────
echo "[2/7] DB 백업..."
cd "${APP_DIR}"
docker compose exec -T db pg_dump -U django npms_db | gzip > "${TEMP_DIR}/db.sql.gz" 2>/dev/null
echo "      DB 완료 ($(du -h ${TEMP_DIR}/db.sql.gz | cut -f1))"

# ── 3. .env 파일 ─────────────────────────────────────────
echo "[3/7] .env 백업..."
cp "${APP_DIR}/.env" "${TEMP_DIR}/dot_env" 2>/dev/null || true
echo "      .env 완료"

# ── 4. docker-compose.yml ────────────────────────────────
echo "[4/7] docker-compose.yml 백업..."
cp "${APP_DIR}/docker-compose.yml" "${TEMP_DIR}/" 2>/dev/null || true
echo "      docker-compose.yml 완료"

# ── 5. SSL 인증서 ────────────────────────────────────────
echo "[5/7] SSL 인증서 백업..."
if [ -d /etc/letsencrypt ]; then
    tar czf "${TEMP_DIR}/ssl.tar.gz" -C /etc letsencrypt 2>/dev/null || true
    echo "      SSL 완료"
else
    echo "      SSL 없음 (건너뜀)"
fi

# ── 6. SSH 키 ────────────────────────────────────────────
echo "[6/7] SSH 키 백업..."
if [ -d /home/pms/.ssh ]; then
    tar czf "${TEMP_DIR}/ssh.tar.gz" -C /home/pms .ssh 2>/dev/null || true
    echo "      SSH 완료"
else
    echo "      SSH 없음 (건너뜀)"
fi

# ── 7. 시스템 설정 ───────────────────────────────────────
echo "[7/7] 시스템 설정 백업..."
mkdir -p "${TEMP_DIR}/sysconf"
crontab -u pms -l > "${TEMP_DIR}/sysconf/crontab_pms.txt" 2>/dev/null || true
crontab -u root -l > "${TEMP_DIR}/sysconf/crontab_root.txt" 2>/dev/null || true
cp /etc/modprobe.d/block-usb-storage.conf "${TEMP_DIR}/sysconf/" 2>/dev/null || true
echo "      시스템 설정 완료"

# ── tar 통합 압축 ────────────────────────────────────────
echo ""
echo "통합 압축 중..."
tar czf "${BACKUP_DIR}/${BACKUP_NAME}.tar.gz" -C "${BACKUP_DIR}" ".tmp_${BACKUP_NAME}"

# ── GPG 암호화 ───────────────────────────────────────────
echo "암호화 중..."
echo "${PASSPHRASE}" | gpg --batch --yes --passphrase-fd 0 \
    --symmetric --cipher-algo AES256 \
    -o "${BACKUP_DIR}/${BACKUP_NAME}.tar.gz.gpg" \
    "${BACKUP_DIR}/${BACKUP_NAME}.tar.gz"

# ── 임시 파일 정리 ───────────────────────────────────────
rm -rf "${TEMP_DIR}"
rm -f "${BACKUP_DIR}/${BACKUP_NAME}.tar.gz"

# ── 오래된 백업 삭제 (30일) ──────────────────────────────
echo "오래된 백업 정리 (${KEEP_DAYS}일 이상)..."
find "${BACKUP_DIR}" -name "npms_full_*.tar.gz.gpg" -mtime +${KEEP_DAYS} -delete 2>/dev/null || true

# ── 결과 ─────────────────────────────────────────────────
FINAL="${BACKUP_DIR}/${BACKUP_NAME}.tar.gz.gpg"
SIZE=$(du -h "${FINAL}" | cut -f1)
echo ""
echo "======================================"
echo "  백업 완료: $(date)"
echo "  파일: ${FINAL}"
echo "  크기: ${SIZE}"
echo "  암호: AES-256 암호화 적용"
echo "======================================"
echo ""
echo "복구 방법:"
echo "  gpg -d ${BACKUP_NAME}.tar.gz.gpg > ${BACKUP_NAME}.tar.gz"
echo "  tar xzf ${BACKUP_NAME}.tar.gz"
