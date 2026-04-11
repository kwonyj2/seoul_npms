from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView
from . import views

app_name = 'accounts'

router = DefaultRouter()
router.register(r'users', views.UserViewSet, basename='user')
router.register(r'sessions', views.ActiveSessionViewSet, basename='session')

urlpatterns = [
    # 템플릿 뷰 (로그인/로그아웃)
    path('login/',  views.LoginView.as_view(),  name='login'),
    path('logout/', views.LogoutView.as_view(), name='logout'),

    # JWT API
    path('token/',         views.CustomTokenObtainPairView.as_view(), name='token_obtain'),
    path('token/refresh/', TokenRefreshView.as_view(),                name='token_refresh'),

    # 2FA
    path('2fa/', views.TwoFactorSetupView.as_view(), name='2fa-setup'),

    # REST API
    path('api/', include(router.urls)),
]
