#!/usr/bin/env python3
"""
학교 네트워크 구성도 자동 분석 & 토폴로지 임포트 스크립트
- API 키 불필요 (Claude Code CLI 인증 사용)
- Rate Limit 자동 감지 → 대기 → 자동 재개
- NMS 모니터링 화면과 진행 현황 연동
Usage:
  python3 /home/kwonyj/network_pms/auto_import.py
  python3 /home/kwonyj/network_pms/auto_import.py --school 가락고등학교
  python3 /home/kwonyj/network_pms/auto_import.py --resume        # 이미 처리된 학교 스킵
  python3 /home/kwonyj/network_pms/auto_import.py --list-pending  # 미처리 학교 목록
"""
import subprocess
import json
import os
import sys
import re
import argparse
import time
from pathlib import Path
from datetime import datetime, timedelta

# ─── 경로 설정 ────────────────────────────────────────────────────────────────
BASE_DIR      = Path(__file__).parent
IMAGE_DIR     = BASE_DIR / 'src/media/data/구성도이미지'
PROGRESS_FILE = BASE_DIR / '.auto_import_progress.json'
COMPOSE_FILE  = BASE_DIR / 'docker-compose.yml'
CLAUDE_BIN    = Path(os.path.expanduser('~/.npm-global/bin/claude'))

# ─── Docker Compose 명령 ──────────────────────────────────────────────────────
DOCKER_EXEC = ['docker', 'compose', '-f', str(COMPOSE_FILE), 'exec', '-T', 'web']

# ─── Rate Limit 감지 키워드 ───────────────────────────────────────────────────
RATE_LIMIT_KEYWORDS = [
    'rate limit', 'ratelimit', 'usage limit', 'quota',
    'too many requests', 'overloaded', 'try again',
    '429', '529', '503', 'exceeded',
]

# ─── 구성도 분석 프롬프트 ──────────────────────────────────────────────────────
PROMPT_TEMPLATE = """파일 {image_path} 를 읽고 네트워크 구성도를 분석해서 정확히 아래 JSON 형식만 출력해줘.
설명, 마크다운 코드블록 없이 순수 JSON만 출력.

{{
  "nodes": [
    {{"name": "장비명", "device_type": "switch|poe_switch|ap|router|firewall|server", "model": "모델명(없으면 빈문자열)", "location": "설치위치(없으면 빈문자열)", "network_type": "교사망|학생망|무선망|전화망|기타망|빈문자열"}}
  ],
  "edges": [
    {{"from": "출발장비명", "to": "도착장비명", "cable_type": "광|Cat6|Cat5e|Cat5|미확인", "network_type": "교사망|학생망|무선망|전화망|기타망|빈문자열"}}
  ]
}}

device_type 기준: firewall=방화벽/UTM, router=라우터/L3, switch=일반스위치, poe_switch=PoE스위치, ap=무선AP, server=서버"""


def load_progress() -> dict:
    if PROGRESS_FILE.exists():
        try:
            return json.loads(PROGRESS_FILE.read_text(encoding='utf-8'))
        except Exception:
            pass
    return {'done': [], 'failed': [], 'skipped': []}


def save_progress(progress: dict):
    PROGRESS_FILE.write_text(json.dumps(progress, ensure_ascii=False, indent=2), encoding='utf-8')


def update_nms_progress(progress_data: dict):
    cmd = DOCKER_EXEC + [
        'python', '-c',
        f'from django.core.cache import cache; cache.set("bulk_diagram_progress", {repr(progress_data)}, timeout=7200)'
    ]
    try:
        subprocess.run(cmd, capture_output=True, timeout=10, cwd=str(BASE_DIR))
    except Exception:
        pass


def get_school_name(filename: str) -> str:
    name = Path(filename).stem
    for prefix in ('구성도_', '네트워크구성도_', '망구성도_'):
        if name.startswith(prefix):
            name = name[len(prefix):]
    return name


def _is_rate_limited(text: str) -> bool:
    """Rate Limit 관련 메시지인지 확인"""
    lower = text.lower()
    return any(kw in lower for kw in RATE_LIMIT_KEYWORDS)


def _test_claude_available() -> bool:
    """Claude CLI가 실제로 응답 가능한지 테스트"""
    try:
        result = subprocess.run(
            [str(CLAUDE_BIN), '-p', '--dangerously-skip-permissions',
             '--output-format', 'text', '--no-session-persistence'],
            input='respond with the single word: OK',
            capture_output=True, text=True, timeout=30,
        )
        out = result.stdout.strip()
        err = result.stderr.strip()
        # 응답이 있고 rate limit 아니면 사용 가능
        return bool(out) and not _is_rate_limited(out + err)
    except Exception:
        return False


def wait_for_rate_limit(check_interval: int = 1800):
    """
    Rate Limit 감지 시 자동 대기 후 재개.
    30분마다 실제 테스트하여 해제되면 즉시 재개.
    최대 6시간 대기.
    """
    max_wait = 6 * 3600  # 최대 6시간
    start    = time.time()
    resume_at = datetime.now() + timedelta(seconds=max_wait)

    print(f'\n{"="*60}')
    print(f'  ⚠️  Claude Rate Limit 감지!')
    print(f'  → 30분마다 자동 체크하여 한도 해제 시 즉시 재개')
    print(f'  → 최대 대기: 6시간 (예상 재개: {resume_at.strftime("%H:%M")})')
    print(f'{"="*60}\n')

    check_count = 0
    while time.time() - start < max_wait:
        time.sleep(check_interval)
        check_count += 1
        elapsed  = int(time.time() - start)
        remaining = max_wait - elapsed
        print(f'[Rate Limit 체크 #{check_count}] 경과: {elapsed//3600}시간 {(elapsed%3600)//60}분 '
              f'| 남은 최대 대기: {remaining//3600}시간 {(remaining%3600)//60}분', flush=True)

        if _test_claude_available():
            print(f'✅ Rate Limit 해제 확인! 작업을 재개합니다.\n')
            return

        print(f'  아직 한도 중... {check_interval//60}분 후 재체크', flush=True)

    print(f'⏰ 최대 대기 시간 초과. 강제 재개합니다.\n')


def analyze_image(image_path: Path) -> dict:
    """Claude Code CLI로 이미지 분석 (최대 3회 재시도, Rate Limit 자동 대기)"""
    prompt    = PROMPT_TEMPLATE.format(image_path=str(image_path))
    last_err  = None
    rate_limited_count = 0

    for attempt in range(1, 4):
        if attempt > 1:
            wait = attempt * 10
            print(f'[재시도 {attempt}/3, {wait}초 대기]', end=' ', flush=True)
            time.sleep(wait)

        result = subprocess.run(
            [str(CLAUDE_BIN), '-p', '--dangerously-skip-permissions',
             '--tools', 'Read', '--output-format', 'text', '--no-session-persistence'],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=240,
            cwd=str(BASE_DIR / 'src'),
        )
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()

        # Rate Limit 감지
        if _is_rate_limited(stdout + stderr) or (not stdout and _is_rate_limited(stderr)):
            rate_limited_count += 1
            if rate_limited_count >= 2:
                # 2회 연속 rate limit → 대기 후 재시도
                wait_for_rate_limit()
                rate_limited_count = 0
            last_err = 'Rate Limit'
            continue

        if not stdout:
            last_err = f'빈 응답. stderr: {stderr[:200]}'
            continue

        # 코드블록 제거
        text = re.sub(r'```json\s*', '', stdout)
        text = re.sub(r'```\s*', '', text)
        text = text.strip()

        try:
            data = json.loads(text)
            if 'nodes' not in data:
                last_err = f'nodes 필드 없음: {text[:80]}'
                continue
            return data
        except json.JSONDecodeError as e:
            # JSON 잘림 복구 시도
            for ending in ['}]}', '}]', '}}']:
                idx = text.rfind(ending)
                if idx != -1:
                    try:
                        data = json.loads(text[:idx + len(ending)])
                        if 'nodes' in data:
                            return data
                    except Exception:
                        pass
            last_err = f'JSON 오류: {e}'
            continue

    raise ValueError(last_err or '분석 실패')


def import_topology(school_name: str, topology: dict) -> str:
    json_str = json.dumps(topology, ensure_ascii=False)
    result = subprocess.run(
        DOCKER_EXEC + ['python', 'manage.py', 'import_topology',
                       '--school', school_name, '--json', json_str],
        capture_output=True, text=True, timeout=60, cwd=str(BASE_DIR),
    )
    output = result.stdout.strip()
    if result.returncode != 0 or not output.startswith('OK'):
        raise ValueError(f'import 실패: {result.stderr[:200] or output}')
    return output


def get_image_files() -> list[Path]:
    return sorted(IMAGE_DIR.glob('구성도_*.jpg')) + sorted(IMAGE_DIR.glob('구성도_*.jpeg'))


def check_school_exists(school_name: str) -> bool:
    escaped = school_name.replace('"', '\\"')
    result = subprocess.run(
        DOCKER_EXEC + ['python', '-c',
                       f'import django; django.setup(); from apps.schools.models import School; '
                       f'print(School.objects.filter(name="{escaped}").exists())'],
        capture_output=True, text=True, timeout=15, cwd=str(BASE_DIR),
    )
    return 'True' in result.stdout


def main():
    parser = argparse.ArgumentParser(description='학교 구성도 자동 분석 & 임포트')
    parser.add_argument('--school',       help='단일 학교만 처리')
    parser.add_argument('--resume',       action='store_true', help='이미 처리된 학교 스킵')
    parser.add_argument('--list-pending', action='store_true', help='미처리 학교 목록 출력')
    parser.add_argument('--delay',        type=float, default=5.0, help='학교 간 대기 시간(초, 기본 5)')
    args = parser.parse_args()

    if not CLAUDE_BIN.exists():
        print(f'[오류] claude CLI를 찾을 수 없음: {CLAUDE_BIN}'); sys.exit(1)
    if not IMAGE_DIR.exists():
        print(f'[오류] 이미지 폴더 없음: {IMAGE_DIR}'); sys.exit(1)

    images = get_image_files()
    if not images:
        print(f'[오류] 이미지 파일 없음: {IMAGE_DIR}'); sys.exit(1)

    progress = load_progress()

    if args.list_pending:
        done_set = set(progress['done'])
        pending  = [get_school_name(f.name) for f in images if get_school_name(f.name) not in done_set]
        print(f'미처리 학교: {len(pending)}개')
        for s in pending:
            print(f'  - {s}')
        return

    if args.school:
        images = [f for f in images if get_school_name(f.name) == args.school]
        if not images:
            print(f'[오류] 해당 학교 이미지 없음: {args.school}'); sys.exit(1)

    done_set = set(progress['done']) if args.resume else set()
    total    = len(images)
    ok_count = fail_count = skip_count = 0
    results  = []

    print(f'\n{"="*60}')
    print(f' 학교 네트워크 구성도 자동 분석 시작')
    print(f' 대상: {total}개 이미지 | 시각: {datetime.now().strftime("%Y-%m-%d %H:%M")}')
    print(f' Rate Limit 자동 감지 및 대기 기능 활성화')
    print(f'{"="*60}')

    nms_progress = {
        'started': True, 'finished': False,
        'total': total, 'done': 0, 'ok': 0, 'skip': 0, 'fail': 0, 'results': [],
    }
    update_nms_progress(nms_progress)

    # 연속 실패 카운터 (Rate Limit 조기 감지용)
    consecutive_failures = 0

    for idx, image_path in enumerate(images, 1):
        school_name = get_school_name(image_path.name)
        print(f'\n[{idx:4d}/{total}] {school_name}', end=' ... ', flush=True)

        if school_name in done_set:
            print('SKIP (이미 처리됨)')
            skip_count += 1
            results.append({'school': school_name, 'status': 'skip', 'note': '이미 처리됨'})
            nms_progress.update({'done': idx, 'skip': skip_count, 'results': results[-200:]})
            update_nms_progress(nms_progress)
            continue

        if not check_school_exists(school_name):
            print('SKIP (DB 미등록)')
            skip_count += 1
            results.append({'school': school_name, 'status': 'skip', 'note': 'DB 미등록 학교'})
            nms_progress.update({'done': idx, 'skip': skip_count, 'results': results[-200:]})
            update_nms_progress(nms_progress)
            continue

        # 연속 실패 5회 → Rate Limit 의심, 선제적 대기
        if consecutive_failures >= 5:
            print(f'\n[경고] 연속 {consecutive_failures}회 실패 → Rate Limit 의심, 대기 시작')
            wait_for_rate_limit()
            consecutive_failures = 0

        try:
            topology = analyze_image(image_path)
            output   = import_topology(school_name, topology)
            print(f'OK  {output}')
            ok_count += 1
            consecutive_failures = 0
            progress['done'].append(school_name)
            save_progress(progress)
            results.append({'school': school_name, 'status': 'ok',
                            'note': output.split('|', 1)[-1] if '|' in output else output})

        except subprocess.TimeoutExpired:
            print('FAIL (timeout)')
            fail_count += 1
            consecutive_failures += 1
            results.append({'school': school_name, 'status': 'fail', 'note': 'timeout'})

        except Exception as e:
            err_msg = str(e)
            print(f'FAIL ({err_msg[:60]})')
            fail_count += 1
            consecutive_failures += 1
            results.append({'school': school_name, 'status': 'fail', 'note': err_msg[:80]})

        nms_progress.update({
            'done': idx, 'ok': ok_count, 'fail': fail_count, 'skip': skip_count,
            'results': results[-200:],
        })
        update_nms_progress(nms_progress)

        if idx < total and args.delay > 0:
            time.sleep(args.delay)

    nms_progress['finished'] = True
    update_nms_progress(nms_progress)

    print(f'\n{"="*60}')
    print(f' 완료: 성공 {ok_count} | 실패 {fail_count} | 스킵 {skip_count} | 합계 {total}')
    print(f'{"="*60}\n')


if __name__ == '__main__':
    main()
