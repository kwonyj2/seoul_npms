#!/bin/bash
# ═══════════════════════════════════════════════════
# NPMS 보안관제 — iptables 자동 차단 스크립트
# 호스트 cron에서 5분마다 실행
#
# 설치:
#   sudo crontab -e
#   */5 * * * * /home/pms/seoul_npms/scripts/apply_firewall.sh >> /var/log/npms_firewall.log 2>&1
# ═══════════════════════════════════════════════════

BLOCK_FILE="/mnt/lvm-cache/firewall/blocked_ips.txt"
CHAIN="NPMS_BLOCK"
LOG_PREFIX="[NPMS_BLOCK] "

# 차단 파일 없으면 종료
if [ ! -f "$BLOCK_FILE" ]; then
    exit 0
fi

# NPMS_BLOCK 체인 생성 (최초 1회)
iptables -N "$CHAIN" 2>/dev/null
# INPUT 체인에 NPMS_BLOCK 점프 규칙 추가 (중복 방지)
iptables -C INPUT -j "$CHAIN" 2>/dev/null || iptables -I INPUT 1 -j "$CHAIN"

# 기존 NPMS_BLOCK 규칙 모두 삭제 (갱신)
iptables -F "$CHAIN"

# 차단 IP 적용
COUNT=0
while IFS= read -r line; do
    # 주석·빈줄 스킵
    [[ "$line" =~ ^#.*$ || -z "$line" ]] && continue
    # IP 형식 검증
    if [[ "$line" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        iptables -A "$CHAIN" -s "$line" -j DROP
        COUNT=$((COUNT + 1))
    fi
done < "$BLOCK_FILE"

echo "$(date '+%Y-%m-%d %H:%M:%S') — $COUNT개 IP 차단 적용"
