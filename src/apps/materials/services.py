# materials 비즈니스 로직
import os
from django.template.loader import render_to_string
from django.conf import settings
from django.utils import timezone


def generate_inbound_pdf(inbound_id):
    """입고증 PDF 생성 — WeasyPrint"""
    from .models import MaterialInbound
    import weasyprint

    inbound = MaterialInbound.objects.select_related('material', 'material__category', 'received_by').get(id=inbound_id)

    html = render_to_string('materials/pdf_inbound.html', {
        'inbound': inbound,
        'now':     timezone.now(),
    })

    pdf_dir = os.path.join(settings.MEDIA_ROOT, 'materials', 'inbound')
    os.makedirs(pdf_dir, exist_ok=True)
    pdf_path = os.path.join(pdf_dir, f'{inbound.inbound_number}.pdf')
    weasyprint.HTML(string=html).write_pdf(pdf_path)

    rel_path = os.path.relpath(pdf_path, settings.MEDIA_ROOT)
    inbound.pdf_path = rel_path
    inbound.save(update_fields=['pdf_path'])
    return rel_path


def generate_outbound_pdf(outbound_id):
    """출고증 PDF 생성 — WeasyPrint"""
    from .models import MaterialOutbound
    import weasyprint

    outbound = MaterialOutbound.objects.select_related(
        'material', 'to_center', 'to_worker', 'issued_by'
    ).get(id=outbound_id)

    html = render_to_string('materials/pdf_outbound.html', {
        'outbound': outbound,
        'now':      timezone.now(),
    })

    pdf_dir = os.path.join(settings.MEDIA_ROOT, 'materials', 'outbound')
    os.makedirs(pdf_dir, exist_ok=True)
    pdf_path = os.path.join(pdf_dir, f'{outbound.outbound_number}.pdf')
    weasyprint.HTML(string=html).write_pdf(pdf_path)

    rel_path = os.path.relpath(pdf_path, settings.MEDIA_ROOT)
    outbound.pdf_path = rel_path
    outbound.save(update_fields=['pdf_path'])
    return rel_path
