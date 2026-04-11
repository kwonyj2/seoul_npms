FROM python:3.11-slim

# 시스템 패키지 설치
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    netcat-openbsd \
    git \
    curl \
    gettext \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    shared-mime-info \
    tesseract-ocr \
    tesseract-ocr-kor \
    poppler-utils \
    fonts-nanum \
    fonts-noto-cjk \
    libreoffice-writer \
    libreoffice-calc \
    libreoffice-impress \
    libreoffice-h2orestart \
    && rm -rf /var/lib/apt/lists/*

# 작업 디렉토리
WORKDIR /app

# 의존성 먼저 복사 (캐시 활용)
COPY src/requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 소스 코드 복사
COPY src/ /app/

# entrypoint 실행 권한
RUN chmod +x /app/docker-entrypoint.sh

EXPOSE 8000
