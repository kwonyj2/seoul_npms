#!/bin/bash
# ═══════════════════════════════════════════════════
# NPMS 자체서명 SSL 인증서 생성
# 사용: sudo bash scripts/generate_ssl.sh
# ═══════════════════════════════════════════════════

SSL_DIR="$(dirname "$0")/../docker/ssl"
mkdir -p "$SSL_DIR"

openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout "$SSL_DIR/server.key" \
    -out "$SSL_DIR/server.crt" \
    -subj "/CN=112.187.158.4/O=NPMS Seoul Education/C=KR/ST=Seoul" \
    -addext "subjectAltName=IP:112.187.158.4,IP:127.0.0.1"

chmod 644 "$SSL_DIR/server.crt"
chmod 600 "$SSL_DIR/server.key"

echo "SSL 인증서 생성 완료:"
ls -la "$SSL_DIR/"
echo ""
echo "유효기간: 365일"
echo "접속 URL: https://112.187.158.4:8443/npms/"
