from rest_framework.pagination import PageNumberPagination

class StandardPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 200


class LargePagination(PageNumberPagination):
    """NAS 파일 등 대량 목록용 — 폴더 내 전체 파일 표시"""
    page_size = 5000
    page_size_query_param = 'page_size'
    max_page_size = 10000
