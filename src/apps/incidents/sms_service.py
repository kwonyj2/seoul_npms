"""
SMS 알림 서비스
- SMS_PROVIDER=console  : 콘솔 출력 (개발용)
- SMS_PROVIDER=solapi   : SOLAPI REST API
- SMS_PROVIDER=aligo    : 알리고 API
"""
import logging
import hmac
import hashlib
import uuid
from datetime import datetime
from django.conf import settings

logger = logging.getLogger(__name__)


def send_sms(to: str, message: str) -> bool:
    """
    단건 SMS 발송
    to: 수신 번호 (010-1234-5678 또는 01012345678)
    message: 발송할 내용 (90바이트 초과 시 LMS 자동 처리)
    반환: 성공 여부
    """
    if not getattr(settings, 'SMS_ENABLED', False):
        logger.info(f"[SMS-disabled] TO={to} | {message[:40]}...")
        return True  # 비활성 상태는 성공으로 처리

    provider = getattr(settings, 'SMS_PROVIDER', 'console')
    try:
        if provider == 'console':
            return _send_console(to, message)
        elif provider == 'solapi':
            return _send_solapi(to, message)
        elif provider == 'aligo':
            return _send_aligo(to, message)
        else:
            logger.warning(f"알 수 없는 SMS 공급자: {provider}")
            return False
    except Exception as exc:
        logger.error(f"SMS 발송 오류 ({provider}): {exc}")
        return False


def send_bulk_sms(recipients: list, message: str) -> dict:
    """
    다건 SMS 발송
    recipients: [{"name": "홍길동", "phone": "01012345678"}, ...]
    반환: {"sent": N, "failed": M}
    """
    sent = failed = 0
    for r in recipients:
        phone = r.get('phone') or r.get('tel') or ''
        if not phone:
            failed += 1
            continue
        if send_sms(phone, message):
            sent += 1
        else:
            failed += 1
    return {"sent": sent, "failed": failed}


# ── 공급자별 구현 ─────────────────────────────────────────────

def _send_console(to: str, message: str) -> bool:
    print(f"\n[SMS] TO={to}\n{message}\n{'─'*40}")
    return True


def _send_solapi(to: str, message: str) -> bool:
    """SOLAPI (구 Cool SMS) REST API"""
    import requests
    api_key    = settings.SMS_API_KEY
    api_secret = settings.SMS_API_SECRET
    sender     = settings.SMS_SENDER_NUMBER

    date_str   = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
    salt       = str(uuid.uuid4()).replace('-', '')[:10]
    raw        = f"date={date_str}&salt={salt}"
    signature  = hmac.new(api_secret.encode(), raw.encode(), hashlib.sha256).hexdigest()
    auth_token = f"HMAC-SHA256 apiKey={api_key}, date={date_str}, salt={salt}, signature={signature}"

    msg_type   = 'SMS' if len(message.encode('euc-kr', errors='replace')) <= 90 else 'LMS'
    payload    = {
        "message": {
            "to":      to.replace('-', ''),
            "from":    sender.replace('-', ''),
            "text":    message,
            "type":    msg_type,
        }
    }
    resp = requests.post(
        "https://api.solapi.com/messages/v4/send",
        json=payload,
        headers={"Authorization": auth_token, "Content-Type": "application/json"},
        timeout=10,
    )
    if resp.status_code == 200:
        return True
    logger.error(f"SOLAPI 오류: {resp.status_code} {resp.text[:200]}")
    return False


def _send_aligo(to: str, message: str) -> bool:
    """알리고 API"""
    import requests
    payload = {
        'key':      settings.SMS_API_KEY,
        'userid':   settings.SMS_API_SECRET,   # 알리고는 userid 사용
        'sender':   settings.SMS_SENDER_NUMBER.replace('-', ''),
        'receiver': to.replace('-', ''),
        'msg':      message,
        'msg_type': 'SMS' if len(message) <= 45 else 'LMS',
        'testmode_yn': 'N',
    }
    resp = requests.post(
        "https://apis.aligo.in/send/",
        data=payload,
        timeout=10,
    )
    result = resp.json()
    if result.get('result_code') == '1':
        return True
    logger.error(f"알리고 오류: {result}")
    return False


# ── 메시지 템플릿 ─────────────────────────────────────────────

def make_incident_assigned_msg(incident) -> str:
    school = incident.school.name if incident.school else '미상'
    category = str(incident.category) if incident.category else '기타'
    title = incident.title or '장애'
    return (
        f"[NPMS] 장애배정 알림\n"
        f"학교: {school}\n"
        f"유형: {category}\n"
        f"내용: {title[:30]}\n"
        f"접수번호: #{incident.pk}"
    )


def make_incident_completed_msg(incident) -> str:
    school = incident.school.name if incident.school else '미상'
    return (
        f"[NPMS] 장애처리 완료\n"
        f"학교: {school}\n"
        f"접수번호: #{incident.pk}\n"
        f"처리 완료되었습니다."
    )


def make_network_event_msg(event) -> str:
    device = event.device
    school = device.school.name if device.school else '미상'
    return (
        f"[NPMS] 네트워크 경보\n"
        f"학교: {school}\n"
        f"장비: {device.name} ({device.ip_address})\n"
        f"이벤트: {event.get_event_type_display()}\n"
        f"심각도: {event.get_severity_display()}"
    )
