from django.urls import path
from . import views

app_name = 'education'

urlpatterns = [
    # 분류
    path('categories/',                         views.api_categories,           name='categories'),
    # 수강자
    path('courses/',                            views.api_courses,              name='courses'),
    path('courses/<int:course_id>/',            views.api_course_detail,        name='course-detail'),
    path('contents/<int:content_id>/progress/', views.api_save_progress,        name='save-progress'),
    path('courses/<int:course_id>/complete/',   views.api_complete_course,      name='complete'),
    path('courses/<int:course_id>/certificate/', views.api_certificate_pdf,     name='certificate'),
    path('my/completions/',                     views.api_my_completions,       name='my-completions'),
    # 관리자
    path('admin/completions/',                  views.api_all_completions,      name='admin-completions'),
    path('admin/courses/',                      views.api_admin_courses,        name='admin-courses'),
    path('admin/courses/<int:course_id>/',      views.api_admin_course_detail,  name='admin-course-detail'),
    path('admin/courses/<int:course_id>/upload/', views.api_upload_content,     name='admin-upload'),
    path('admin/contents/<int:content_id>/',    views.api_delete_content,       name='admin-del-content'),
]
