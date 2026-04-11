# assets 비즈니스 로직
import os
from django.template.loader import render_to_string
from django.conf import settings
from django.utils import timezone


def generate_inbound_pdf(inbound_id):
    """장비 입고증 PDF 생성 — WeasyPrint"""
    from .models import AssetInbound
    import weasyprint

    inbound = AssetInbound.objects.select_related(
        'asset', 'asset__model', 'asset__model__category',
        'from_center', 'to_center', 'created_by',
    ).prefetch_related('asset__model__asset_model_category').get(id=inbound_id)

    html = render_to_string('assets/pdf_inbound.html', {
        'inbound': inbound,
        'now':     timezone.now(),
    })

    pdf_dir = os.path.join(settings.MEDIA_ROOT, 'assets', 'inbound')
    os.makedirs(pdf_dir, exist_ok=True)
    pdf_path = os.path.join(pdf_dir, f'{inbound.inbound_number}.pdf')
    weasyprint.HTML(string=html).write_pdf(pdf_path)

    rel_path = os.path.relpath(pdf_path, settings.MEDIA_ROOT)
    inbound.pdf_path = rel_path
    inbound.save(update_fields=['pdf_path'])
    return rel_path


def generate_outbound_pdf(outbound_id):
    """장비 출고증 PDF 생성 — WeasyPrint"""
    from .models import AssetOutbound
    import weasyprint

    outbound = AssetOutbound.objects.select_related(
        'asset', 'asset__model', 'asset__model__category',
        'from_center', 'to_center', 'created_by',
    ).get(id=outbound_id)

    html = render_to_string('assets/pdf_outbound.html', {
        'outbound': outbound,
        'now':      timezone.now(),
    })

    pdf_dir = os.path.join(settings.MEDIA_ROOT, 'assets', 'outbound')
    os.makedirs(pdf_dir, exist_ok=True)
    pdf_path = os.path.join(pdf_dir, f'{outbound.outbound_number}.pdf')
    weasyprint.HTML(string=html).write_pdf(pdf_path)

    rel_path = os.path.relpath(pdf_path, settings.MEDIA_ROOT)
    outbound.pdf_path = rel_path
    outbound.save(update_fields=['pdf_path'])
    return rel_path


def generate_return_pdf(return_id):
    """장비 반납증 PDF 생성 — WeasyPrint"""
    from .models import AssetReturn
    import weasyprint

    ret = AssetReturn.objects.select_related(
        'asset', 'asset__model', 'asset__model__category',
        'from_school_center', 'to_center', 'created_by',
    ).get(id=return_id)

    html = render_to_string('assets/pdf_return.html', {
        'ret': ret,
        'now': timezone.now(),
    })

    pdf_dir = os.path.join(settings.MEDIA_ROOT, 'assets', 'returns')
    os.makedirs(pdf_dir, exist_ok=True)
    pdf_path = os.path.join(pdf_dir, f'{ret.return_number}.pdf')
    weasyprint.HTML(string=html).write_pdf(pdf_path)

    rel_path = os.path.relpath(pdf_path, settings.MEDIA_ROOT)
    ret.pdf_path = rel_path
    ret.save(update_fields=['pdf_path'])
    return rel_path
