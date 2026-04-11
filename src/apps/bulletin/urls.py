from rest_framework.routers import DefaultRouter
from .views import PostViewSet

app_name = 'bulletin'

router = DefaultRouter()
router.register(r'posts', PostViewSet, basename='post')

urlpatterns = router.urls
