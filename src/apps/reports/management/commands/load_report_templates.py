"""
보고서 템플릿 초기 데이터 로드
python manage.py load_report_templates
"""
from django.core.management.base import BaseCommand
from apps.reports.models import ReportTemplate


# ──────────────────────────────────────────────────────────
# HTML 템플릿 공통 스타일
# ──────────────────────────────────────────────────────────
_BASE_STYLE = """
<style>
  @page { size: A4; margin: 20mm 18mm; }
  body  { font-family: 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif;
          font-size: 10.5pt; color: #000; }
  h2    { text-align: center; font-size: 15pt; font-weight: bold;
          margin: 0 0 4px; letter-spacing: 2px; }
  .sub  { text-align: center; font-size: 9.5pt; color: #444; margin-bottom: 14px; }
  table { width: 100%; border-collapse: collapse; margin-bottom: 10px; }
  th, td { border: 1px solid #000; padding: 4px 7px; font-size: 10pt; }
  th    { background: #f0f0f0; font-weight: bold; text-align: center; }
  .hd   { background: #d0d8f0; font-size: 10.5pt; text-align: center; }
  .hd-g { background: #d0f0d8; font-size: 10.5pt; text-align: center; }
  .hd-y { background: #fff0cc; font-size: 10.5pt; text-align: center; }
  .sign-box  { display: flex; gap: 12px; justify-content: flex-end; margin-top: 10px; }
  .sign-cell { border: 1px solid #000; width: 120px; text-align: center; padding: 4px; }
  .sign-cell .lbl { font-size: 9pt; color: #555; margin-bottom: 2px; }
  .sign-cell img  { max-width: 100px; max-height: 55px; margin-top: 3px; }
  .sign-cell .blank { height: 55px; }
  .stamp { border: 2px solid #c00; border-radius: 50%; width: 68px; height: 68px;
           display: inline-flex; align-items: center; justify-content: center;
           font-size: 9.5pt; color: #c00; font-weight: bold;
           margin-left: 16px; vertical-align: middle; }
  .footer { margin-top: 18px; text-align: center; font-size: 8.5pt; color: #777; }
  .ok  { color: #157347; font-weight: bold; }
  .ng  { color: #c00;    font-weight: bold; }
  .na  { color: #888; }
  .center { text-align: center; }
  .right  { text-align: right; }
  .bold   { font-weight: bold; }
  .w20 { width: 20%; }
  .w30 { width: 30%; }
  .w15 { width: 15%; }
</style>
"""

# ──────────────────────────────────────────────────────────
# 1. 스위치 설치 확인서
# ──────────────────────────────────────────────────────────
SWITCH_INSTALL_HTML = """<!DOCTYPE html>
<html lang="ko">
<head><meta charset="UTF-8">""" + _BASE_STYLE + """</head>
<body>

<h2>스위치 설치 확인서</h2>
<p class="sub">Network Switch Installation Certificate</p>

<table>
  <tr>
    <th class="w20">학교명</th>
    <td>{{ report.school.name }}</td>
    <th class="w20">설치일자</th>
    <td>{{ data.install_date|default:"-" }}</td>
  </tr>
  <tr>
    <th>담당기사</th>
    <td>{{ report.created_by.name|default:"-" }}</td>
    <th>지원청</th>
    <td>{{ report.school.support_center.name|default:"-" }}</td>
  </tr>
  <tr>
    <th>관련장애번호</th>
    <td>{{ report.incident.incident_number|default:"-" }}</td>
    <th>작성일시</th>
    <td>{% now "Y년 m월 d일" %}</td>
  </tr>
</table>

<table>
  <thead>
    <tr><th colspan="6" class="hd">설치 장비 정보</th></tr>
    <tr>
      <th>제조사</th><th>모델명</th><th>시리얼번호</th>
      <th>포트수</th><th>설치위치</th><th>수량</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td class="center">{{ data.manufacturer|default:"-" }}</td>
      <td class="center">{{ data.model|default:"-" }}</td>
      <td class="center">{{ data.serial_number|default:"-" }}</td>
      <td class="center">{{ data.port_count|default:"-" }}</td>
      <td>{{ data.install_location|default:"-" }}</td>
      <td class="center bold">{{ data.quantity|default:"1" }}</td>
    </tr>
  </tbody>
</table>

<table>
  <thead><tr><th colspan="4" class="hd">포트 연결 정보</th></tr></thead>
  <tbody>
    <tr>
      <th class="w15">업링크 포트</th>
      <td>{{ data.uplink_port|default:"-" }}</td>
      <th class="w15">업링크 연결</th>
      <td>{{ data.uplink_connection|default:"-" }}</td>
    </tr>
    <tr>
      <th>VLAN 설정</th>
      <td>{{ data.vlan_config|default:"-" }}</td>
      <th>IP 주소</th>
      <td>{{ data.ip_address|default:"-" }}</td>
    </tr>
    <tr>
      <th>사용 포트 수</th>
      <td>{{ data.used_ports|default:"-" }}</td>
      <th>여유 포트 수</th>
      <td>{{ data.spare_ports|default:"-" }}</td>
    </tr>
  </tbody>
</table>

<table>
  <thead><tr><th colspan="4" class="hd">설치 후 점검 결과</th></tr></thead>
  <tbody>
    <tr>
      <th class="w30">항목</th><th class="w20">결과</th>
      <th class="w30">항목</th><th>결과</th>
    </tr>
    <tr>
      <td>전원 공급 확인</td>
      <td class="center {% if data.chk_power == 'OK' %}ok{% else %}ng{% endif %}">{{ data.chk_power|default:"미확인" }}</td>
      <td>링크 상태 확인</td>
      <td class="center {% if data.chk_link == 'OK' %}ok{% else %}ng{% endif %}">{{ data.chk_link|default:"미확인" }}</td>
    </tr>
    <tr>
      <td>통신 테스트 (Ping)</td>
      <td class="center {% if data.chk_ping == 'OK' %}ok{% else %}ng{% endif %}">{{ data.chk_ping|default:"미확인" }}</td>
      <td>업링크 속도</td>
      <td class="center">{{ data.chk_speed|default:"-" }}</td>
    </tr>
    <tr>
      <td>콘솔 접속 확인</td>
      <td class="center {% if data.chk_console == 'OK' %}ok{% else %}ng{% endif %}">{{ data.chk_console|default:"미확인" }}</td>
      <td>설정 저장 확인</td>
      <td class="center {% if data.chk_save == 'OK' %}ok{% else %}ng{% endif %}">{{ data.chk_save|default:"미확인" }}</td>
    </tr>
  </tbody>
</table>

{% if data.notes %}
<table>
  <tr><th style="width:10%;">특이사항</th><td>{{ data.notes }}</td></tr>
</table>
{% endif %}

<div class="sign-box">
  {% for sig in report.signatures.all %}
  <div class="sign-cell">
    <div class="lbl">{{ sig.role|default:sig.signer_name }}</div>
    {% if sig.signature_data %}
      <img src="{{ sig.signature_data }}" alt="서명">
    {% else %}
      <div class="blank"></div>
    {% endif %}
    <div>{{ sig.signer_name }}</div>
  </div>
  {% empty %}
  <div class="sign-cell">
    <div class="lbl">담당기사</div>
    <div class="blank"></div>
    <div>{{ report.created_by.name|default:"" }}</div>
  </div>
  <div class="sign-cell">
    <div class="lbl">확인자</div>
    <div class="blank"></div>
    <div></div>
  </div>
  {% endfor %}
  <div style="display:inline-block;vertical-align:middle;">
    <div class="stamp">서울시<br>교육청</div>
  </div>
</div>

<p class="footer">
  본 확인서는 자재·장비 관리 시스템(NPMS)에서 자동 생성되었습니다.<br>
  생성일시: {% now "Y-m-d H:i:s" %}
</p>

</body>
</html>"""


# ──────────────────────────────────────────────────────────
# 2. 소규모 네트워크 포설 확인서
# ──────────────────────────────────────────────────────────
CABLE_HTML = """<!DOCTYPE html>
<html lang="ko">
<head><meta charset="UTF-8">""" + _BASE_STYLE + """</head>
<body>

<h2>소규모 네트워크 포설 확인서</h2>
<p class="sub">Small-Scale Cable Construction Certificate</p>

<table>
  <tr>
    <th class="w20">학교명</th>
    <td>{{ report.school.name }}</td>
    <th class="w20">공사일자</th>
    <td>{{ data.work_date|default:"-" }}</td>
  </tr>
  <tr>
    <th>담당기사</th>
    <td>{{ report.created_by.name|default:"-" }}</td>
    <th>지원청</th>
    <td>{{ report.school.support_center.name|default:"-" }}</td>
  </tr>
  <tr>
    <th>관련장애번호</th>
    <td>{{ report.incident.incident_number|default:"-" }}</td>
    <th>작성일시</th>
    <td>{% now "Y년 m월 d일" %}</td>
  </tr>
</table>

<table>
  <thead><tr><th colspan="6" class="hd-g">공사 내역</th></tr>
    <tr>
      <th>케이블 종류</th><th>규격</th><th>공사구간(시작)</th>
      <th>공사구간(종료)</th><th>수량</th><th>단위</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td class="center">{{ data.cable_type|default:"-" }}</td>
      <td class="center">{{ data.cable_spec|default:"-" }}</td>
      <td>{{ data.from_location|default:"-" }}</td>
      <td>{{ data.to_location|default:"-" }}</td>
      <td class="center bold">{{ data.quantity|default:"-" }}</td>
      <td class="center">{{ data.unit|default:"m" }}</td>
    </tr>
  </tbody>
</table>

<table>
  <thead><tr><th colspan="4" class="hd-g">자재 사용 내역</th></tr></thead>
  <tbody>
    <tr>
      <th class="w30">자재명</th><th class="w20">규격</th>
      <th class="w20">수량</th><th>비고</th>
    </tr>
    {% if data.materials %}
      {% for m in data.materials %}
      <tr>
        <td>{{ m.name|default:"-" }}</td>
        <td class="center">{{ m.spec|default:"-" }}</td>
        <td class="center">{{ m.qty|default:"-" }}</td>
        <td>{{ m.note|default:"" }}</td>
      </tr>
      {% endfor %}
    {% else %}
    <tr>
      <td>{{ data.material_name|default:"-" }}</td>
      <td class="center">{{ data.material_spec|default:"-" }}</td>
      <td class="center">{{ data.material_qty|default:"-" }}</td>
      <td></td>
    </tr>
    {% endif %}
  </tbody>
</table>

<table>
  <thead><tr><th colspan="4" class="hd-g">시공 결과</th></tr></thead>
  <tbody>
    <tr>
      <th class="w30">항목</th><th class="w20">결과</th>
      <th class="w30">항목</th><th>결과</th>
    </tr>
    <tr>
      <td>케이블 포설 상태</td>
      <td class="center {% if data.chk_laying == '양호' %}ok{% else %}ng{% endif %}">{{ data.chk_laying|default:"미확인" }}</td>
      <td>커넥터 압착 상태</td>
      <td class="center {% if data.chk_crimp == '양호' %}ok{% else %}ng{% endif %}">{{ data.chk_crimp|default:"미확인" }}</td>
    </tr>
    <tr>
      <td>통신 연결 테스트</td>
      <td class="center {% if data.chk_comm == '양호' %}ok{% else %}ng{% endif %}">{{ data.chk_comm|default:"미확인" }}</td>
      <td>케이블 레이블링</td>
      <td class="center {% if data.chk_label == '완료' %}ok{% else %}ng{% endif %}">{{ data.chk_label|default:"미완료" }}</td>
    </tr>
    <tr>
      <td>통신속도 측정 결과</td>
      <td>{{ data.speed_result|default:"-" }}</td>
      <td>정리정돈 상태</td>
      <td class="center {% if data.chk_cleanup == '완료' %}ok{% else %}ng{% endif %}">{{ data.chk_cleanup|default:"미완료" }}</td>
    </tr>
  </tbody>
</table>

{% if data.before_photo or data.after_photo %}
<table>
  <tr>
    <th style="width:10%;">공사 전</th><td>{{ data.before_photo|default:"사진 첨부" }}</td>
    <th style="width:10%;">공사 후</th><td>{{ data.after_photo|default:"사진 첨부" }}</td>
  </tr>
</table>
{% endif %}

{% if data.notes %}
<table>
  <tr><th style="width:10%;">특이사항</th><td>{{ data.notes }}</td></tr>
</table>
{% endif %}

<div class="sign-box">
  {% for sig in report.signatures.all %}
  <div class="sign-cell">
    <div class="lbl">{{ sig.role|default:sig.signer_name }}</div>
    {% if sig.signature_data %}
      <img src="{{ sig.signature_data }}" alt="서명">
    {% else %}
      <div class="blank"></div>
    {% endif %}
    <div>{{ sig.signer_name }}</div>
  </div>
  {% empty %}
  <div class="sign-cell">
    <div class="lbl">시공기사</div>
    <div class="blank"></div>
    <div>{{ report.created_by.name|default:"" }}</div>
  </div>
  <div class="sign-cell">
    <div class="lbl">학교 확인자</div>
    <div class="blank"></div>
    <div></div>
  </div>
  {% endfor %}
  <div style="display:inline-block;vertical-align:middle;">
    <div class="stamp">서울시<br>교육청</div>
  </div>
</div>

<p class="footer">
  본 확인서는 자재·장비 관리 시스템(NPMS)에서 자동 생성되었습니다.<br>
  생성일시: {% now "Y-m-d H:i:s" %}
</p>

</body>
</html>"""


# ──────────────────────────────────────────────────────────
# 3. 정기점검 보고서
# ──────────────────────────────────────────────────────────
REGULAR_HTML = """<!DOCTYPE html>
<html lang="ko">
<head><meta charset="UTF-8">""" + _BASE_STYLE + """</head>
<body>

<h2>정기점검 보고서</h2>
<p class="sub">Regular Inspection Report</p>

<table>
  <tr>
    <th class="w20">학교명</th>
    <td>{{ report.school.name }}</td>
    <th class="w20">점검일자</th>
    <td>{{ data.inspect_date|default:"-" }}</td>
  </tr>
  <tr>
    <th>담당기사</th>
    <td>{{ report.created_by.name|default:"-" }}</td>
    <th>지원청</th>
    <td>{{ report.school.support_center.name|default:"-" }}</td>
  </tr>
  <tr>
    <th>점검유형</th>
    <td>{{ data.inspect_type|default:"정기점검" }}</td>
    <th>작성일시</th>
    <td>{% now "Y년 m월 d일" %}</td>
  </tr>
</table>

<table>
  <thead>
    <tr><th colspan="5" class="hd-y">네트워크 장비 점검</th></tr>
    <tr>
      <th>장비유형</th><th>설치위치</th><th>동작상태</th>
      <th>이상내용</th><th>조치내용</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>코어 스위치</td>
      <td>{{ data.core_switch_location|default:"서버실" }}</td>
      <td class="center {% if data.core_switch_status == '정상' %}ok{% elif data.core_switch_status == '이상' %}ng{% else %}na{% endif %}">
        {{ data.core_switch_status|default:"정상" }}</td>
      <td>{{ data.core_switch_issue|default:"-" }}</td>
      <td>{{ data.core_switch_action|default:"-" }}</td>
    </tr>
    <tr>
      <td>엑세스 스위치</td>
      <td>{{ data.access_switch_location|default:"-" }}</td>
      <td class="center {% if data.access_switch_status == '정상' %}ok{% elif data.access_switch_status == '이상' %}ng{% else %}na{% endif %}">
        {{ data.access_switch_status|default:"정상" }}</td>
      <td>{{ data.access_switch_issue|default:"-" }}</td>
      <td>{{ data.access_switch_action|default:"-" }}</td>
    </tr>
    <tr>
      <td>무선 AP</td>
      <td>{{ data.ap_location|default:"-" }}</td>
      <td class="center {% if data.ap_status == '정상' %}ok{% elif data.ap_status == '이상' %}ng{% else %}na{% endif %}">
        {{ data.ap_status|default:"정상" }}</td>
      <td>{{ data.ap_issue|default:"-" }}</td>
      <td>{{ data.ap_action|default:"-" }}</td>
    </tr>
    <tr>
      <td>라우터/방화벽</td>
      <td>{{ data.fw_location|default:"서버실" }}</td>
      <td class="center {% if data.fw_status == '정상' %}ok{% elif data.fw_status == '이상' %}ng{% else %}na{% endif %}">
        {{ data.fw_status|default:"정상" }}</td>
      <td>{{ data.fw_issue|default:"-" }}</td>
      <td>{{ data.fw_action|default:"-" }}</td>
    </tr>
  </tbody>
</table>

<table>
  <thead>
    <tr><th colspan="4" class="hd-y">점검 체크리스트</th></tr>
    <tr>
      <th>점검항목</th><th>결과</th>
      <th>점검항목</th><th>결과</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>인터넷 속도 측정</td>
      <td class="center">{{ data.chk_speed|default:"-" }}</td>
      <td>장비 먼지/청소 상태</td>
      <td class="center {% if data.chk_clean == '양호' %}ok{% else %}ng{% endif %}">{{ data.chk_clean|default:"미확인" }}</td>
    </tr>
    <tr>
      <td>LED 상태 확인</td>
      <td class="center {% if data.chk_led == '정상' %}ok{% else %}ng{% endif %}">{{ data.chk_led|default:"미확인" }}</td>
      <td>케이블 정리 상태</td>
      <td class="center {% if data.chk_cable == '양호' %}ok{% else %}ng{% endif %}">{{ data.chk_cable|default:"미확인" }}</td>
    </tr>
    <tr>
      <td>전원 공급 장치</td>
      <td class="center {% if data.chk_power == '정상' %}ok{% else %}ng{% endif %}">{{ data.chk_power|default:"미확인" }}</td>
      <td>로그 확인</td>
      <td class="center {% if data.chk_log == '이상없음' %}ok{% else %}ng{% endif %}">{{ data.chk_log|default:"미확인" }}</td>
    </tr>
    <tr>
      <td>펌웨어 버전</td>
      <td>{{ data.firmware_version|default:"-" }}</td>
      <td>보안 패치 현황</td>
      <td class="center {% if data.chk_security == '최신' %}ok{% else %}ng{% endif %}">{{ data.chk_security|default:"미확인" }}</td>
    </tr>
  </tbody>
</table>

<table>
  <tr>
    <th style="width:12%;">이상사항 요약</th>
    <td>{{ data.issue_summary|default:"특이사항 없음" }}</td>
  </tr>
  <tr>
    <th>조치내용</th>
    <td>{{ data.action_summary|default:"-" }}</td>
  </tr>
  <tr>
    <th>다음 점검 예정</th>
    <td>{{ data.next_inspect_date|default:"-" }}</td>
  </tr>
</table>

<div class="sign-box">
  {% for sig in report.signatures.all %}
  <div class="sign-cell">
    <div class="lbl">{{ sig.role|default:sig.signer_name }}</div>
    {% if sig.signature_data %}
      <img src="{{ sig.signature_data }}" alt="서명">
    {% else %}
      <div class="blank"></div>
    {% endif %}
    <div>{{ sig.signer_name }}</div>
  </div>
  {% empty %}
  <div class="sign-cell">
    <div class="lbl">점검기사</div>
    <div class="blank"></div>
    <div>{{ report.created_by.name|default:"" }}</div>
  </div>
  <div class="sign-cell">
    <div class="lbl">학교 담당자</div>
    <div class="blank"></div>
    <div></div>
  </div>
  {% endfor %}
  <div style="display:inline-block;vertical-align:middle;">
    <div class="stamp">서울시<br>교육청</div>
  </div>
</div>

<p class="footer">
  본 보고서는 자재·장비 관리 시스템(NPMS)에서 자동 생성되었습니다.<br>
  생성일시: {% now "Y-m-d H:i:s" %}
</p>

</body>
</html>"""


# ──────────────────────────────────────────────────────────
# 4. 분기별 점검 보고서
# ──────────────────────────────────────────────────────────
QUARTERLY_HTML = """<!DOCTYPE html>
<html lang="ko">
<head><meta charset="UTF-8">""" + _BASE_STYLE + """</head>
<body>

<h2>분기별 점검 보고서</h2>
<p class="sub">Quarterly Inspection Report</p>

<table>
  <tr>
    <th class="w20">학교명</th>
    <td>{{ report.school.name }}</td>
    <th class="w20">점검 분기</th>
    <td>{{ data.year|default:"-" }}년 {{ data.quarter|default:"-" }}분기</td>
  </tr>
  <tr>
    <th>담당기사</th>
    <td>{{ report.created_by.name|default:"-" }}</td>
    <th>지원청</th>
    <td>{{ report.school.support_center.name|default:"-" }}</td>
  </tr>
  <tr>
    <th>점검기간</th>
    <td>{{ data.period_start|default:"-" }} ~ {{ data.period_end|default:"-" }}</td>
    <th>작성일시</th>
    <td>{% now "Y년 m월 d일" %}</td>
  </tr>
</table>

<table>
  <thead><tr><th colspan="4" class="hd">분기 장애 현황</th></tr></thead>
  <tbody>
    <tr>
      <th class="w30">총 장애 건수</th>
      <td class="center bold">{{ data.total_incidents|default:"0" }} 건</td>
      <th class="w30">처리 완료</th>
      <td class="center ok">{{ data.resolved_incidents|default:"0" }} 건</td>
    </tr>
    <tr>
      <th>평균 처리 시간</th>
      <td class="center">{{ data.avg_resolve_time|default:"-" }}</td>
      <th>미처리 건수</th>
      <td class="center {% if data.pending_incidents != '0' %}ng{% endif %}">{{ data.pending_incidents|default:"0" }} 건</td>
    </tr>
    <tr>
      <th>주요 장애 유형</th>
      <td colspan="3">{{ data.main_incident_types|default:"-" }}</td>
    </tr>
  </tbody>
</table>

<table>
  <thead>
    <tr><th colspan="6" class="hd">장비 현황 요약</th></tr>
    <tr>
      <th>장비유형</th><th>총 수량</th><th>정상</th>
      <th>교체 필요</th><th>노후화(%)</th><th>비고</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td class="center">코어 스위치</td>
      <td class="center">{{ data.core_total|default:"-" }}</td>
      <td class="center ok">{{ data.core_ok|default:"-" }}</td>
      <td class="center ng">{{ data.core_replace|default:"-" }}</td>
      <td class="center">{{ data.core_old_pct|default:"-" }}%</td>
      <td>{{ data.core_note|default:"" }}</td>
    </tr>
    <tr>
      <td class="center">엑세스 스위치</td>
      <td class="center">{{ data.access_total|default:"-" }}</td>
      <td class="center ok">{{ data.access_ok|default:"-" }}</td>
      <td class="center ng">{{ data.access_replace|default:"-" }}</td>
      <td class="center">{{ data.access_old_pct|default:"-" }}%</td>
      <td>{{ data.access_note|default:"" }}</td>
    </tr>
    <tr>
      <td class="center">무선 AP</td>
      <td class="center">{{ data.ap_total|default:"-" }}</td>
      <td class="center ok">{{ data.ap_ok|default:"-" }}</td>
      <td class="center ng">{{ data.ap_replace|default:"-" }}</td>
      <td class="center">{{ data.ap_old_pct|default:"-" }}%</td>
      <td>{{ data.ap_note|default:"" }}</td>
    </tr>
  </tbody>
</table>

<table>
  <thead><tr><th colspan="3" class="hd">네트워크 성능 측정</th></tr></thead>
  <tbody>
    <tr>
      <th class="w30">평균 인터넷 속도</th>
      <td>{{ data.avg_speed|default:"-" }}</td>
      <th class="w30">평균 패킷 손실률</th>
      <td>{{ data.avg_packet_loss|default:"-" }}%</td>
    </tr>
    <tr>
      <th>평균 응답속도(RTT)</th>
      <td>{{ data.avg_rtt|default:"-" }} ms</td>
      <th>가용성</th>
      <td>{{ data.availability|default:"-" }}%</td>
    </tr>
  </tbody>
</table>

<table>
  <tr>
    <th style="width:15%;">분기 종합 의견</th>
    <td>{{ data.summary|default:"-" }}</td>
  </tr>
  <tr>
    <th>개선 필요사항</th>
    <td>{{ data.improvements|default:"-" }}</td>
  </tr>
  <tr>
    <th>차기 분기 계획</th>
    <td>{{ data.next_quarter_plan|default:"-" }}</td>
  </tr>
</table>

<div class="sign-box">
  {% for sig in report.signatures.all %}
  <div class="sign-cell">
    <div class="lbl">{{ sig.role|default:sig.signer_name }}</div>
    {% if sig.signature_data %}
      <img src="{{ sig.signature_data }}" alt="서명">
    {% else %}
      <div class="blank"></div>
    {% endif %}
    <div>{{ sig.signer_name }}</div>
  </div>
  {% empty %}
  <div class="sign-cell">
    <div class="lbl">담당기사</div>
    <div class="blank"></div>
    <div>{{ report.created_by.name|default:"" }}</div>
  </div>
  <div class="sign-cell">
    <div class="lbl">팀장</div>
    <div class="blank"></div>
    <div></div>
  </div>
  {% endfor %}
  <div style="display:inline-block;vertical-align:middle;">
    <div class="stamp">서울시<br>교육청</div>
  </div>
</div>

<p class="footer">
  본 보고서는 자재·장비 관리 시스템(NPMS)에서 자동 생성되었습니다.<br>
  생성일시: {% now "Y-m-d H:i:s" %}
</p>

</body>
</html>"""


# ──────────────────────────────────────────────────────────
# 필드 스키마 정의
# ──────────────────────────────────────────────────────────
SWITCH_INSTALL_SCHEMA = {
    "fields": [
        {"name": "install_date",     "label": "설치일자",      "type": "date",   "required": True},
        {"name": "manufacturer",     "label": "제조사",        "type": "text",   "required": True},
        {"name": "model",            "label": "모델명",        "type": "text",   "required": True},
        {"name": "serial_number",    "label": "시리얼번호",    "type": "text",   "required": True},
        {"name": "port_count",       "label": "포트수",        "type": "number", "required": True},
        {"name": "install_location", "label": "설치위치",      "type": "text",   "required": True},
        {"name": "quantity",         "label": "수량",          "type": "number", "required": True, "default": 1},
        {"name": "uplink_port",      "label": "업링크 포트",   "type": "text"},
        {"name": "uplink_connection","label": "업링크 연결장비","type": "text"},
        {"name": "vlan_config",      "label": "VLAN 설정",     "type": "text"},
        {"name": "ip_address",       "label": "관리 IP",       "type": "text"},
        {"name": "used_ports",       "label": "사용 포트 수",  "type": "number"},
        {"name": "spare_ports",      "label": "여유 포트 수",  "type": "number"},
        {"name": "chk_power",        "label": "전원 확인",     "type": "select", "options": ["OK", "NG"]},
        {"name": "chk_link",         "label": "링크 상태",     "type": "select", "options": ["OK", "NG"]},
        {"name": "chk_ping",         "label": "Ping 테스트",   "type": "select", "options": ["OK", "NG"]},
        {"name": "chk_speed",        "label": "업링크 속도",   "type": "text"},
        {"name": "chk_console",      "label": "콘솔 접속",     "type": "select", "options": ["OK", "NG"]},
        {"name": "chk_save",         "label": "설정 저장",     "type": "select", "options": ["OK", "NG"]},
        {"name": "notes",            "label": "특이사항",      "type": "textarea"},
    ]
}

CABLE_SCHEMA = {
    "fields": [
        {"name": "work_date",      "label": "공사일자",      "type": "date",   "required": True},
        {"name": "cable_type",     "label": "케이블 종류",   "type": "select", "required": True,
         "options": ["UTP CAT.5e", "UTP CAT.6", "UTP CAT.6A", "광케이블 SM", "광케이블 MM", "동축케이블"]},
        {"name": "cable_spec",     "label": "규격",          "type": "text"},
        {"name": "from_location",  "label": "공사구간(시작)","type": "text",   "required": True},
        {"name": "to_location",    "label": "공사구간(종료)","type": "text",   "required": True},
        {"name": "quantity",       "label": "수량",          "type": "number", "required": True},
        {"name": "unit",           "label": "단위",          "type": "select", "options": ["m", "본", "식"]},
        {"name": "material_name",  "label": "주요 자재명",   "type": "text"},
        {"name": "material_spec",  "label": "자재 규격",     "type": "text"},
        {"name": "material_qty",   "label": "자재 수량",     "type": "number"},
        {"name": "chk_laying",     "label": "포설 상태",     "type": "select", "options": ["양호", "불량"]},
        {"name": "chk_crimp",      "label": "압착 상태",     "type": "select", "options": ["양호", "불량"]},
        {"name": "chk_comm",       "label": "통신 테스트",   "type": "select", "options": ["양호", "불량"]},
        {"name": "chk_label",      "label": "레이블링",      "type": "select", "options": ["완료", "미완료"]},
        {"name": "speed_result",   "label": "속도 측정",     "type": "text"},
        {"name": "chk_cleanup",    "label": "정리 상태",     "type": "select", "options": ["완료", "미완료"]},
        {"name": "notes",          "label": "특이사항",      "type": "textarea"},
    ]
}

REGULAR_SCHEMA = {
    "fields": [
        {"name": "inspect_date",          "label": "점검일자",         "type": "date",   "required": True},
        {"name": "inspect_type",          "label": "점검유형",         "type": "select", "options": ["정기점검", "특별점검", "수시점검"]},
        {"name": "core_switch_location",  "label": "코어스위치 위치",  "type": "text"},
        {"name": "core_switch_status",    "label": "코어스위치 상태",  "type": "select", "options": ["정상", "이상", "점검불가"]},
        {"name": "core_switch_issue",     "label": "코어스위치 이상내용","type": "text"},
        {"name": "core_switch_action",    "label": "코어스위치 조치내용","type": "text"},
        {"name": "access_switch_location","label": "엑세스스위치 위치","type": "text"},
        {"name": "access_switch_status",  "label": "엑세스스위치 상태","type": "select", "options": ["정상", "이상", "점검불가"]},
        {"name": "access_switch_issue",   "label": "이상내용",         "type": "text"},
        {"name": "access_switch_action",  "label": "조치내용",         "type": "text"},
        {"name": "ap_location",           "label": "AP 위치",          "type": "text"},
        {"name": "ap_status",             "label": "AP 상태",          "type": "select", "options": ["정상", "이상", "점검불가"]},
        {"name": "ap_issue",              "label": "AP 이상내용",      "type": "text"},
        {"name": "ap_action",             "label": "AP 조치내용",      "type": "text"},
        {"name": "fw_location",           "label": "방화벽 위치",      "type": "text"},
        {"name": "fw_status",             "label": "방화벽 상태",      "type": "select", "options": ["정상", "이상", "점검불가"]},
        {"name": "fw_issue",              "label": "방화벽 이상내용",  "type": "text"},
        {"name": "fw_action",             "label": "방화벽 조치내용",  "type": "text"},
        {"name": "chk_speed",             "label": "인터넷 속도",      "type": "text"},
        {"name": "chk_led",               "label": "LED 상태",         "type": "select", "options": ["정상", "이상"]},
        {"name": "chk_power",             "label": "전원 상태",        "type": "select", "options": ["정상", "이상"]},
        {"name": "firmware_version",      "label": "펌웨어 버전",      "type": "text"},
        {"name": "chk_clean",             "label": "청소 상태",        "type": "select", "options": ["양호", "불량"]},
        {"name": "chk_cable",             "label": "케이블 정리",      "type": "select", "options": ["양호", "불량"]},
        {"name": "chk_log",               "label": "로그 확인",        "type": "select", "options": ["이상없음", "이상있음"]},
        {"name": "chk_security",          "label": "보안 패치",        "type": "select", "options": ["최신", "업데이트필요"]},
        {"name": "issue_summary",         "label": "이상사항 요약",    "type": "textarea"},
        {"name": "action_summary",        "label": "조치내용",         "type": "textarea"},
        {"name": "next_inspect_date",     "label": "다음 점검 예정일", "type": "date"},
    ]
}

QUARTERLY_SCHEMA = {
    "fields": [
        {"name": "year",             "label": "연도",           "type": "number", "required": True},
        {"name": "quarter",          "label": "분기",           "type": "select", "required": True, "options": ["1", "2", "3", "4"]},
        {"name": "period_start",     "label": "점검기간 시작",  "type": "date"},
        {"name": "period_end",       "label": "점검기간 종료",  "type": "date"},
        {"name": "total_incidents",  "label": "총 장애 건수",   "type": "number"},
        {"name": "resolved_incidents","label": "처리 완료",     "type": "number"},
        {"name": "pending_incidents","label": "미처리 건수",    "type": "number"},
        {"name": "avg_resolve_time", "label": "평균 처리 시간", "type": "text"},
        {"name": "main_incident_types","label":"주요 장애 유형","type": "text"},
        {"name": "core_total",       "label": "코어스위치 수량","type": "number"},
        {"name": "core_ok",          "label": "코어스위치 정상","type": "number"},
        {"name": "core_replace",     "label": "코어스위치 교체필요","type": "number"},
        {"name": "core_old_pct",     "label": "코어스위치 노후화율","type": "number"},
        {"name": "access_total",     "label": "엑세스스위치 수량","type": "number"},
        {"name": "access_ok",        "label": "엑세스스위치 정상","type": "number"},
        {"name": "access_replace",   "label": "엑세스스위치 교체필요","type": "number"},
        {"name": "access_old_pct",   "label": "엑세스스위치 노후화율","type": "number"},
        {"name": "ap_total",         "label": "AP 수량",        "type": "number"},
        {"name": "ap_ok",            "label": "AP 정상",        "type": "number"},
        {"name": "ap_replace",       "label": "AP 교체필요",    "type": "number"},
        {"name": "ap_old_pct",       "label": "AP 노후화율",    "type": "number"},
        {"name": "avg_speed",        "label": "평균 인터넷 속도","type": "text"},
        {"name": "avg_packet_loss",  "label": "평균 패킷 손실률","type": "number"},
        {"name": "avg_rtt",          "label": "평균 RTT",       "type": "number"},
        {"name": "availability",     "label": "가용성(%)",      "type": "number"},
        {"name": "summary",          "label": "분기 종합 의견", "type": "textarea"},
        {"name": "improvements",     "label": "개선 필요사항",  "type": "textarea"},
        {"name": "next_quarter_plan","label": "차기 분기 계획", "type": "textarea"},
    ]
}


TEMPLATES = [
    {
        "code":          "switch_install_v1",
        "name":          "스위치 설치 확인서",
        "report_type":   "switch_install",
        "template_html": SWITCH_INSTALL_HTML,
        "fields_schema": SWITCH_INSTALL_SCHEMA,
    },
    {
        "code":          "cable_work_v1",
        "name":          "소규모 네트워크 포설 확인서",
        "report_type":   "cable",
        "template_html": CABLE_HTML,
        "fields_schema": CABLE_SCHEMA,
    },
    {
        "code":          "regular_inspect_v1",
        "name":          "정기점검 보고서",
        "report_type":   "regular",
        "template_html": REGULAR_HTML,
        "fields_schema": REGULAR_SCHEMA,
    },
    {
        "code":          "quarterly_inspect_v1",
        "name":          "분기별 점검 보고서",
        "report_type":   "quarterly",
        "template_html": QUARTERLY_HTML,
        "fields_schema": QUARTERLY_SCHEMA,
    },
]


class Command(BaseCommand):
    help = '보고서 템플릿 초기 데이터를 로드합니다.'

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true',
                            help='이미 존재하는 템플릿도 덮어씁니다.')

    def handle(self, *args, **options):
        force = options['force']
        created = updated = skipped = 0

        for t in TEMPLATES:
            obj, is_new = ReportTemplate.objects.get_or_create(
                code=t['code'],
                defaults={
                    'name':          t['name'],
                    'report_type':   t['report_type'],
                    'template_html': t['template_html'],
                    'fields_schema': t['fields_schema'],
                    'is_active':     True,
                }
            )
            if is_new:
                created += 1
                self.stdout.write(self.style.SUCCESS(f'  [생성] {t["name"]} ({t["code"]})'))
            elif force:
                obj.name          = t['name']
                obj.report_type   = t['report_type']
                obj.template_html = t['template_html']
                obj.fields_schema = t['fields_schema']
                obj.is_active     = True
                obj.save()
                updated += 1
                self.stdout.write(self.style.WARNING(f'  [갱신] {t["name"]} ({t["code"]})'))
            else:
                skipped += 1
                self.stdout.write(f'  [건너뜀] {t["name"]} ({t["code"]}) — 이미 존재 (--force 로 덮어쓰기)')

        self.stdout.write(self.style.SUCCESS(
            f'\n완료: 생성 {created}개, 갱신 {updated}개, 건너뜀 {skipped}개'
        ))
