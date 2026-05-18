"""
센터 필터링 유틸리티
고객/현장기사/상주 인력은 소속 교육지원청 데이터만 조회 가능
"""

# 센터 필터링 대상 역할
CENTER_FILTERED_ROLES = ('customer', 'worker', 'resident_central', 'resident_tech', 'resident_edu')


def needs_center_filter(user):
    """해당 사용자가 센터 필터링 대상인지 확인"""
    return (
        user.is_authenticated
        and user.role in CENTER_FILTERED_ROLES
        and user.support_center_id is not None
    )


def get_center_id(user):
    """사용자의 소속 센터 ID 반환. 필터 불필요 시 None."""
    if needs_center_filter(user):
        return user.support_center_id
    return None


def filter_by_center(queryset, user, field='support_center'):
    """queryset에 센터 필터를 적용.
    field: 모델에서 support_center를 가리키는 필드 경로
           예: 'support_center', 'school__support_center'
    """
    center_id = get_center_id(user)
    if center_id is None:
        return queryset
    return queryset.filter(**{f'{field}_id': center_id})
