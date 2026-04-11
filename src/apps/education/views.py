"""
교육관리 뷰
- education_view : 메인 템플릿 페이지
- API: 과정 목록, 콘텐츠, 진도 저장, 이수 처리, 이수증 PDF
"""
import io
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse, FileResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
import json

from .models import (
    EducationCategory, EducationCourse, EducationContent,
    EducationProgress, EducationCompletion,
)


@login_required
def education_view(request):
    """교육 메인 페이지"""
    categories = EducationCategory.objects.filter(is_active=True).prefetch_related(
        'courses__contents'
    )
    return render(request, 'education/index.html', {'categories': categories})


# ── API ──────────────────────────────────────────────────────────────────────

@login_required
def api_courses(request):
    """카테고리별 교육 과정 목록"""
    cat_id = request.GET.get('category')
    qs = EducationCourse.objects.filter(is_active=True).select_related('category')
    if cat_id:
        qs = qs.filter(category_id=cat_id)

    # 현재 사용자 이수 여부
    completed_ids = set(
        EducationCompletion.objects.filter(user=request.user).values_list('course_id', flat=True)
    )

    rows = []
    for c in qs:
        rows.append({
            'id':               c.id,
            'title':            c.title,
            'description':      c.description,
            'instructor':       c.instructor,
            'duration_minutes': c.duration_minutes,
            'pass_percent':     c.pass_percent,
            'is_required':      c.is_required,
            'content_count':    c.contents.count(),
            'is_completed':     c.id in completed_ids,
            'category_name':    c.category.name,
            'category_color':   c.category.color,
        })
    return JsonResponse({'courses': rows})


@login_required
def api_course_detail(request, course_id):
    """과정 상세 + 콘텐츠 목록 + 내 진도"""
    course = get_object_or_404(EducationCourse, id=course_id, is_active=True)
    contents = course.contents.all()

    # 내 진도
    progress_map = {
        p.content_id: p
        for p in EducationProgress.objects.filter(user=request.user, content__course=course)
    }
    completion = EducationCompletion.objects.filter(user=request.user, course=course).first()

    content_list = []
    for ct in contents:
        pr = progress_map.get(ct.id)
        content_list.append({
            'id':               ct.id,
            'title':            ct.title,
            'content_type':     ct.content_type,
            'file_url':         ct.file_url,
            'duration_seconds': ct.duration_seconds,
            'order':            ct.order,
            'watch_percent':    pr.watch_percent if pr else 0,
            'last_position':    pr.last_position if pr else 0,
        })

    return JsonResponse({
        'course': {
            'id':               course.id,
            'title':            course.title,
            'description':      course.description,
            'instructor':       course.instructor,
            'duration_minutes': course.duration_minutes,
            'pass_percent':     course.pass_percent,
            'is_required':      course.is_required,
        },
        'contents':    content_list,
        'is_completed': completion is not None,
        'certificate_no': completion.certificate_no if completion else None,
    })


@csrf_exempt
@login_required
@require_http_methods(['POST'])
def api_save_progress(request, content_id):
    """동영상 시청 진도 저장"""
    content = get_object_or_404(EducationContent, id=content_id)
    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': '잘못된 요청'}, status=400)

    watch_seconds = int(body.get('watch_seconds', 0))
    last_position = int(body.get('last_position', 0))
    duration      = content.duration_seconds or 1
    watch_percent = min(100, int(watch_seconds / duration * 100))

    pr, _ = EducationProgress.objects.update_or_create(
        user=request.user, content=content,
        defaults={
            'watch_seconds': watch_seconds,
            'watch_percent': watch_percent,
            'last_position': last_position,
        }
    )

    # 이수 조건 확인: 과정 내 모든 콘텐츠 평균 시청률 ≥ pass_percent
    course = content.course
    all_contents = course.contents.all()
    if all_contents.exists():
        progress_list = EducationProgress.objects.filter(
            user=request.user, content__in=all_contents
        )
        total_percent = sum(p.watch_percent for p in progress_list)
        avg_percent = total_percent // all_contents.count()
        can_complete = avg_percent >= course.pass_percent
    else:
        can_complete = False

    return JsonResponse({
        'watch_percent': watch_percent,
        'can_complete':  can_complete,
    })


@csrf_exempt
@login_required
@require_http_methods(['POST'])
def api_complete_course(request, course_id):
    """교육 이수 처리"""
    course = get_object_or_404(EducationCourse, id=course_id, is_active=True)

    # 이미 이수
    existing = EducationCompletion.objects.filter(user=request.user, course=course).first()
    if existing:
        return JsonResponse({'certificate_no': existing.certificate_no, 'already': True})

    # 이수 조건 검증
    all_contents = course.contents.all()
    if all_contents.exists():
        progress_list = EducationProgress.objects.filter(
            user=request.user, content__in=all_contents
        )
        total_percent = sum(p.watch_percent for p in progress_list)
        avg_percent = total_percent // all_contents.count()
        if avg_percent < course.pass_percent:
            return JsonResponse(
                {'error': f'이수 기준 미달 (현재 {avg_percent}% / 기준 {course.pass_percent}%)'},
                status=400
            )

    completion = EducationCompletion.objects.create(
        user=request.user,
        course=course,
        score=100,
    )
    return JsonResponse({'certificate_no': completion.certificate_no, 'already': False})


@login_required
def api_certificate_pdf(request, course_id):
    """이수증 PDF 생성 및 다운로드"""
    course = get_object_or_404(EducationCourse, id=course_id)
    completion = get_object_or_404(EducationCompletion, user=request.user, course=course)

    buffer = _generate_certificate_pdf(completion)
    filename = f'이수증_{completion.certificate_no}.pdf'
    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename*=UTF-8\'\'{filename}'
    return response


def _generate_certificate_pdf(completion):
    """ReportLab 기반 이수증 PDF 생성 (맑은 고딕)"""
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from django.conf import settings
    from django.utils import timezone as tz
    import os

    # 한글 폰트 등록 — 우선순위 순
    font_regular = 'Helvetica'
    font_bold    = 'Helvetica-Bold'
    font_paths = [
        (os.path.join(settings.BASE_DIR, 'static', 'fonts', 'malgun.ttf'),
         os.path.join(settings.BASE_DIR, 'static', 'fonts', 'malgunbd.ttf')),
        ('/usr/share/fonts/truetype/nanum/NanumGothic.ttf',
         '/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf'),
    ]
    for reg_path, bold_path in font_paths:
        if os.path.exists(reg_path):
            try:
                pdfmetrics.registerFont(TTFont('KorRegular', reg_path))
                font_regular = 'KorRegular'
                if os.path.exists(bold_path):
                    pdfmetrics.registerFont(TTFont('KorBold', bold_path))
                    font_bold = 'KorBold'
                else:
                    font_bold = 'KorRegular'
                break
            except Exception:
                pass

    buffer = io.BytesIO()
    w, h = A4          # 595.27 x 841.89 pt
    c = canvas.Canvas(buffer, pagesize=A4)

    # ── 배경 ──────────────────────────────────────
    # 상단 컬러 헤더 바
    c.setFillColor(colors.HexColor('#1e3a8a'))
    c.rect(0, h - 45*mm, w, 45*mm, fill=1, stroke=0)

    # 외곽 이중 테두리
    c.setStrokeColor(colors.HexColor('#1e3a8a'))
    c.setLineWidth(2.5)
    c.rect(12*mm, 12*mm, w - 24*mm, h - 24*mm, fill=0)
    c.setStrokeColor(colors.HexColor('#93c5fd'))
    c.setLineWidth(1)
    c.rect(15*mm, 15*mm, w - 30*mm, h - 30*mm, fill=0)

    # ── 제목 ──────────────────────────────────────
    c.setFont(font_bold, 28)
    c.setFillColor(colors.white)
    c.drawCentredString(w / 2, h - 28*mm, '교 육 이 수 증')

    # 부제목
    c.setFont(font_regular, 11)
    c.setFillColor(colors.HexColor('#bfdbfe'))
    c.drawCentredString(w / 2, h - 38*mm, 'CERTIFICATE OF COMPLETION')

    # ── 이수증 번호 ────────────────────────────────
    c.setFont(font_regular, 9)
    c.setFillColor(colors.HexColor('#64748b'))
    c.drawRightString(w - 20*mm, h - 52*mm, f'No. {completion.certificate_no}')

    # ── 정보 테이블 ────────────────────────────────
    user   = completion.user
    course = completion.course

    rows = [
        ('성  명',    user.name),
        ('소속기관',  '세종아이티엘컨소시엄'),
        ('교육과정',  course.title),
        ('교육분류',  course.category.name),
        ('교육시간',  f'{course.duration_minutes}분' if course.duration_minutes else '—'),
        ('이수점수',  f'{completion.score}점'),
        ('이수일자',  completion.completed_at.strftime('%Y년 %m월 %d일')),
    ]

    row_h   = 16*mm
    tbl_top = h - 65*mm
    lbl_w   = 32*mm
    tbl_x   = 25*mm
    tbl_w   = w - 50*mm

    for i, (label, value) in enumerate(rows):
        y_top = tbl_top - i * row_h
        y_bot = y_top - row_h

        # 라벨 배경
        bg = colors.HexColor('#eff6ff') if i % 2 == 0 else colors.HexColor('#f8fafc')
        c.setFillColor(colors.HexColor('#dbeafe'))
        c.rect(tbl_x, y_bot, lbl_w, row_h, fill=1, stroke=0)
        # 값 배경
        c.setFillColor(bg)
        c.rect(tbl_x + lbl_w, y_bot, tbl_w - lbl_w, row_h, fill=1, stroke=0)
        # 테두리
        c.setStrokeColor(colors.HexColor('#e2e8f0'))
        c.setLineWidth(0.5)
        c.rect(tbl_x, y_bot, tbl_w, row_h, fill=0)

        # 라벨 텍스트
        c.setFont(font_bold, 10)
        c.setFillColor(colors.HexColor('#1e40af'))
        c.drawCentredString(tbl_x + lbl_w / 2, y_bot + 5*mm, label)

        # 값 텍스트
        c.setFont(font_regular, 11)
        c.setFillColor(colors.HexColor('#0f172a'))
        c.drawString(tbl_x + lbl_w + 5*mm, y_bot + 5*mm, value)

    # ── 안내 문구 ──────────────────────────────────
    bottom_y = tbl_top - len(rows) * row_h - 12*mm
    c.setFont(font_regular, 11)
    c.setFillColor(colors.HexColor('#1e3a8a'))
    c.drawCentredString(
        w / 2, bottom_y,
        '위 사람은 위의 교육과정을 성실히 이수하였기에 이 이수증을 수여합니다.'
    )

    # ── 발급일 ────────────────────────────────────
    sig_y = bottom_y - 18*mm
    c.setFont(font_regular, 11)
    c.setFillColor(colors.HexColor('#334155'))
    c.drawCentredString(w / 2, sig_y, tz.localdate().strftime('%Y년  %m월  %d일'))

    # ── 발급 기관 (하단 고정) ──────────────────────
    org_y = 45*mm
    c.setFont(font_bold, 14)
    c.setFillColor(colors.HexColor('#1e3a8a'))
    c.drawCentredString(w / 2, org_y, '세종아이티엘 컨소시엄')

    # 기관명 위아래 구분선
    c.setStrokeColor(colors.HexColor('#1e3a8a'))
    c.setLineWidth(1)
    line_half = 55*mm
    c.line(w/2 - line_half, org_y + 8*mm, w/2 + line_half, org_y + 8*mm)
    c.line(w/2 - line_half, org_y - 5*mm, w/2 + line_half, org_y - 5*mm)

    # ── 하단 워터마크 ──────────────────────────────
    c.setFont(font_regular, 8)
    c.setFillColor(colors.HexColor('#94a3b8'))
    c.drawCentredString(w / 2, 22*mm, f'이 이수증은 세종아이티엘 컨소시엄에서 자동 발급되었습니다 · {completion.certificate_no}')

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer


# ── 관리자 API ────────────────────────────────────────────────────────────────

@csrf_exempt
@login_required
def api_admin_courses(request):
    """관리자: 교육 과정 목록/생성"""
    if request.user.role not in ('superadmin', 'admin'):
        return JsonResponse({'error': '권한 없음'}, status=403)

    if request.method == 'GET':
        qs = EducationCourse.objects.select_related('category').order_by('-created_at')
        rows = [{
            'id': c.id, 'title': c.title, 'category': c.category.name,
            'is_active': c.is_active, 'is_required': c.is_required,
            'content_count': c.contents.count(),
            'completion_count': c.completions.count(),
        } for c in qs]
        return JsonResponse({'courses': rows})

    elif request.method == 'POST':
        try:
            body = json.loads(request.body)
        except Exception:
            return JsonResponse({'error': '잘못된 요청'}, status=400)
        cat_id = body.get('category_id')
        title  = body.get('title', '').strip()
        if not cat_id or not title:
            return JsonResponse({'error': '분류·교육명 필수'}, status=400)
        course = EducationCourse.objects.create(
            category_id=cat_id,
            title=title,
            description=body.get('description', ''),
            instructor=body.get('instructor', ''),
            duration_minutes=int(body.get('duration_minutes', 0)),
            pass_percent=int(body.get('pass_percent', 80)),
            is_required=bool(body.get('is_required', False)),
            created_by=request.user,
        )
        return JsonResponse({'id': course.id, 'title': course.title}, status=201)

    return JsonResponse({'error': '허용되지 않는 메서드'}, status=405)


@csrf_exempt
@login_required
def api_admin_course_detail(request, course_id):
    """관리자: 교육 과정 수정/삭제"""
    if request.user.role not in ('superadmin', 'admin'):
        return JsonResponse({'error': '권한 없음'}, status=403)
    course = get_object_or_404(EducationCourse, id=course_id)

    if request.method == 'PATCH':
        try:
            body = json.loads(request.body)
        except Exception:
            return JsonResponse({'error': '잘못된 요청'}, status=400)
        for field in ('title', 'description', 'instructor', 'duration_minutes',
                      'pass_percent', 'is_required', 'is_active'):
            if field in body:
                setattr(course, field, body[field])
        course.save()
        return JsonResponse({'ok': True})

    elif request.method == 'DELETE':
        course.delete()
        return JsonResponse({'ok': True})

    return JsonResponse({'error': '허용되지 않는 메서드'}, status=405)


@csrf_exempt
@login_required
def api_upload_content(request, course_id):
    """관리자: 콘텐츠(동영상/자료) 업로드"""
    if request.user.role not in ('superadmin', 'admin'):
        return JsonResponse({'error': '권한 없음'}, status=403)
    course = get_object_or_404(EducationCourse, id=course_id)

    if request.method == 'POST':
        title        = request.POST.get('title', '').strip()
        content_type = request.POST.get('content_type', 'document')
        external_url = request.POST.get('external_url', '')
        order        = int(request.POST.get('order', 0))
        duration_s   = int(request.POST.get('duration_seconds', 0))
        file_obj     = request.FILES.get('file')

        if not title:
            return JsonResponse({'error': '제목 필수'}, status=400)

        ct = EducationContent.objects.create(
            course=course, title=title, content_type=content_type,
            file=file_obj, external_url=external_url,
            duration_seconds=duration_s, order=order,
        )
        return JsonResponse({'id': ct.id, 'title': ct.title, 'file_url': ct.file_url}, status=201)

    return JsonResponse({'error': '허용되지 않는 메서드'}, status=405)


@csrf_exempt
@login_required
def api_delete_content(request, content_id):
    """관리자: 콘텐츠 삭제(DELETE) / 영상 길이 수정(PATCH)"""
    if request.user.role not in ('superadmin', 'admin'):
        return JsonResponse({'error': '권한 없음'}, status=403)
    ct = get_object_or_404(EducationContent, id=content_id)
    if request.method == 'DELETE':
        ct.delete()
        return JsonResponse({'ok': True})
    if request.method == 'PATCH':
        import json
        try:
            body = json.loads(request.body)
        except ValueError:
            return JsonResponse({'error': '잘못된 JSON'}, status=400)
        if 'duration_seconds' in body:
            ct.duration_seconds = max(0, int(body['duration_seconds']))
            ct.save(update_fields=['duration_seconds'])
        return JsonResponse({'id': ct.id, 'duration_seconds': ct.duration_seconds})
    return JsonResponse({'error': '허용되지 않는 메서드'}, status=405)


@login_required
def api_my_completions(request):
    """내 이수 목록"""
    completions = EducationCompletion.objects.filter(user=request.user).select_related('course__category')
    rows = [{
        'id':             c.id,
        'course_id':      c.course_id,
        'course_title':   c.course.title,
        'category':       c.course.category.name,
        'certificate_no': c.certificate_no,
        'completed_at':   c.completed_at.strftime('%Y-%m-%d %H:%M'),
        'score':          c.score,
    } for c in completions]
    return JsonResponse({'completions': rows})


@login_required
def api_all_completions(request):
    """관리자: 전체 이수 현황 조회"""
    if request.user.role not in ('superadmin', 'admin'):
        return JsonResponse({'error': '권한 없음'}, status=403)

    course_id = request.GET.get('course_id')
    qs = EducationCompletion.objects.select_related('user', 'course__category').order_by('-completed_at')
    if course_id:
        qs = qs.filter(course_id=course_id)

    rows = [{
        'id':             c.id,
        'user_name':      c.user.name,
        'user_role':      c.user.get_role_display() if hasattr(c.user, 'get_role_display') else c.user.role,
        'center':         c.user.support_center.name if c.user.support_center else '—',
        'course_title':   c.course.title,
        'category':       c.course.category.name,
        'certificate_no': c.certificate_no,
        'completed_at':   c.completed_at.strftime('%Y-%m-%d'),
        'score':          c.score,
    } for c in qs]
    return JsonResponse({'completions': rows, 'total': len(rows)})


@login_required
def api_categories(request):
    """교육 분류 목록"""
    cats = EducationCategory.objects.filter(is_active=True).values(
        'id', 'name', 'icon', 'color', 'order'
    )
    return JsonResponse({'categories': list(cats)})
