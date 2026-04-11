#!/bin/bash
set -e

echo "======================================"
echo "  NPMS Django Server Starting..."
echo "======================================"

# PostgreSQL 준비 대기
echo "[1/4] Waiting for PostgreSQL..."
while ! nc -z "$DB_HOST" 5432; do
  sleep 1
done
echo "      PostgreSQL is ready."

# Redis 준비 대기
echo "[2/4] Waiting for Redis..."
while ! nc -z "$REDIS_HOST" 6379; do
  sleep 1
done
echo "      Redis is ready."

# 마이그레이션
echo "[3/4] Running migrations..."
python manage.py makemigrations --noinput
python manage.py migrate --noinput

# 정적 파일 수집
echo "[4/4] Collecting static files..."
python manage.py collectstatic --noinput

# 슈퍼유저 자동 생성 (환경변수 설정 시)
if [ -n "$DJANGO_SUPERUSER_USERNAME" ]; then
  python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username='$DJANGO_SUPERUSER_USERNAME').exists():
    User.objects.create_superuser('$DJANGO_SUPERUSER_USERNAME', '$DJANGO_SUPERUSER_EMAIL', '$DJANGO_SUPERUSER_PASSWORD')
    print('Superuser created.')
else:
    print('Superuser already exists.')
"
fi

echo "======================================"
echo "  Starting Gunicorn..."
echo "======================================"

exec gunicorn config.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 3 \
    --worker-class gthread \
    --threads 2 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile -
