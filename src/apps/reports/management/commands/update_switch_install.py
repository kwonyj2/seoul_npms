"""
스위치 설치확인서 템플릿 업데이트 (fields_schema + template_html 재설계)
python manage.py update_switch_install
"""
from django.core.management.base import BaseCommand
from apps.reports.models import ReportTemplate


NEW_FIELDS_SCHEMA = {
    "fields": [
        {
            "name": "install_date",
            "label": "설치일자",
            "type": "date",
            "section": "기본 정보",
            "required": True
        },
        {
            "name": "quantity",
            "label": "설치수량",
            "type": "number",
            "section": "기본 정보",
            "required": True,
            "default": "1"
        },
        {
            "name": "devices",
            "label": "설치 장비 목록",
            "type": "switch_devices",
            "section": "기본 정보",
            "wide": True
        },
        {
            "name": "notes",
            "label": "비고",
            "type": "textarea",
            "section": "기타",
            "placeholder": "특이사항을 입력하세요"
        }
    ]
}


NEW_TEMPLATE_HTML = """\
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<style>
  @page { size: A4; margin: 20mm 15mm; }
  body  { font-family: NanumGothic, '나눔고딕', sans-serif;
          font-size: 9.5pt; color: #000; }
  h1   { text-align: center; font-size: 18pt; font-weight: bold;
          margin: 0 0 14px; letter-spacing: 6px; }
  table { width: 100%; border-collapse: collapse; margin-bottom: 10px; }
  th, td { border: 1px solid #000; padding: 4px 6px; font-size: 9pt;
           vertical-align: middle; }
  th    { background: #f0f0f0; font-weight: bold; text-align: center;
          white-space: nowrap; }
  .section-title { font-size: 10pt; font-weight: bold; margin: 12px 0 4px; }
  .center { text-align: center; }
  /* 장비 행 페이지 절단 방지 */
  tbody tr { page-break-inside: avoid; }
  /* 사진 고정 크기 */
  td.photo-cell { height: 130px; text-align: center; }
  td.photo-cell img { max-width: 100%; max-height: 120px;
                      display: block; margin: 0 auto;
                      border: 1px solid #ccc; }
  td.photo-cell .no-photo { color: #bbb; font-size: 8pt;
                             line-height: 120px; text-align: center; }
  /* 확인자 서명 */
  td.sign-area { height: 80px; text-align: center; vertical-align: middle; }
  td.sign-area img { max-height: 75px; max-width: 100%;
                     display: block; margin: 0 auto; }
  .footer { margin-top: 12px; text-align: center; font-size: 7.5pt; color: #888; }
</style>
</head>
<body>

<h1>{% if data.doc_type == "ap" %}AP 설치 확인서{% else %}스위치 설치 확인서{% endif %}</h1>

<table>
  <tr>
    <th style="width:12%;">교육지원청</th>
    <td style="width:26%;">{{ report.school.support_center.name|default:"-" }}</td>
    <th style="width:8%;">학교명</th>
    <td style="width:30%;">{{ report.school.name }}</td>
    <th style="width:8%;">설치일</th>
    <td>{{ data.install_date|default:"-" }}</td>
  </tr>
</table>

<p class="section-title">□ 설치장비</p>
<table>
  <thead>
    <tr>
      <th style="width:5%;">No.</th>
      <th style="width:12%;">건물</th>
      <th style="width:7%;">층</th>
      <th style="width:14%;">설치장소</th>
      <th style="width:10%;">장비ID</th>
      <th style="width:18%;">교체전 장비</th>
      <th style="width:20%;">설치장비</th>
      <th style="width:14%;">제조번호</th>
    </tr>
  </thead>
  <tbody>
    {% if data.devices %}
      {% for d in data.devices %}
      <tr>
        <td class="center">{{ forloop.counter }}</td>
        <td class="center">{{ d.building|default:"-" }}</td>
        <td class="center">{{ d.floor|default:"-" }}</td>
        <td class="center">{{ d.location|default:"-" }}</td>
        <td class="center">{{ d.asset_id|default:"-" }}</td>
        <td class="center">{{ d.prev_model|default:"-" }}{% if d.prev_manufacturer %}<br><span style="font-size:7.5pt;color:#555;">{{ d.prev_manufacturer }}</span>{% endif %}</td>
        <td class="center">{{ d.model_name|default:"-" }}{% if d.manufacturer %}<br><span style="font-size:7.5pt;color:#555;">{{ d.manufacturer }}</span>{% endif %}</td>
        <td class="center" style="font-size:8pt;">{{ d.serial_number|default:"-" }}</td>
      </tr>
      {% endfor %}
    {% else %}
    <tr><td colspan="8" class="center">장비 정보 없음</td></tr>
    {% endif %}
  </tbody>
</table>

<p class="section-title">□ 설치장비 사진</p>
<table>
  <thead>
    <tr>
      <th style="width:5%;">No.</th>
      <th style="width:33%;">교체 전</th>
      <th style="width:33%;">교체 후</th>
      <th style="width:29%;">제조번호</th>
    </tr>
  </thead>
  <tbody>
    {% if data.devices %}
      {% for d in data.devices %}
      <tr>
        <td class="center" style="vertical-align:middle;">{{ forloop.counter }}</td>
        <td class="photo-cell">
          {% if d.photo_before_b64 %}<img src="{{ d.photo_before_b64 }}" alt="교체전">
          {% else %}<div class="no-photo">사진 없음</div>{% endif %}
        </td>
        <td class="photo-cell">
          {% if d.photo_after_b64 %}<img src="{{ d.photo_after_b64 }}" alt="교체후">
          {% else %}<div class="no-photo">사진 없음</div>{% endif %}
        </td>
        <td class="photo-cell">
          {% if d.photo_serial_b64 %}<img src="{{ d.photo_serial_b64 }}" alt="제조번호">
          {% else %}<div class="no-photo">사진 없음</div>{% endif %}
        </td>
      </tr>
      {% endfor %}
    {% else %}
    <tr><td colspan="4" class="center">사진 없음</td></tr>
    {% endif %}
  </tbody>
</table>

{% if data.notes %}
<table>
  <tr><th style="width:8%;">비고</th><td>{{ data.notes }}</td></tr>
</table>
{% endif %}

<p class="section-title">□ 확인자</p>
{% with sig_itl=data.signature_itl sig_sch=data.signature_school %}
<table>
  <tr>
    <th style="width:10%;">소&nbsp;&nbsp;&nbsp;속</th>
    <td style="width:38%;">{{ sig_itl.org|default:"세종아이티엘 컨소시엄" }}</td>
    <th style="width:10%;">소&nbsp;&nbsp;&nbsp;속</th>
    <td>{{ sig_sch.org|default:report.school.name }}</td>
  </tr>
  <tr>
    <th>담당자</th>
    <td>{{ sig_itl.name|default:report.created_by.name|default:"" }}</td>
    <th>담당자</th>
    <td>{{ sig_sch.name|default:"" }}</td>
  </tr>
  <tr>
    <th>연락처</th>
    <td>{{ sig_itl.phone|default:"" }}</td>
    <th>연락처</th>
    <td>{{ sig_sch.phone|default:"" }}</td>
  </tr>
  <tr>
    <th colspan="2" class="center">설치자 서명</th>
    <th colspan="2" class="center">확인자 서명</th>
  </tr>
  <tr>
    <td colspan="2" class="sign-area">
      {% if sig_itl.data %}<img src="{{ sig_itl.data }}" alt="설치자 서명">{% endif %}
    </td>
    <td colspan="2" class="sign-area">
      {% if sig_sch.data %}<img src="{{ sig_sch.data }}" alt="확인자 서명">{% endif %}
    </td>
  </tr>
</table>
{% endwith %}

<p class="footer">
  본 확인서는 자재·장비 관리 시스템(NPMS)에서 자동 생성되었습니다. &nbsp;
  생성일시: {% now "Y-m-d H:i:s" %}
</p>

</body>
</html>"""


class Command(BaseCommand):
    help = '스위치 설치확인서 템플릿 재설계 (fields_schema + template_html 업데이트)'

    def handle(self, *args, **options):
        try:
            tmpl = ReportTemplate.objects.get(report_type='switch_install')
        except ReportTemplate.DoesNotExist:
            self.stderr.write('switch_install 템플릿을 찾을 수 없습니다.')
            return
        except ReportTemplate.MultipleObjectsReturned:
            tmpl = ReportTemplate.objects.filter(report_type='switch_install').first()

        tmpl.fields_schema = NEW_FIELDS_SCHEMA
        tmpl.template_html = NEW_TEMPLATE_HTML
        tmpl.save(update_fields=['fields_schema', 'template_html'])
        self.stdout.write(self.style.SUCCESS(
            f'스위치 설치확인서 템플릿 (id={tmpl.id}) 업데이트 완료'
        ))
