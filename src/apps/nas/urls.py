from rest_framework.routers import DefaultRouter
from .views import FolderViewSet, FileViewSet

app_name = 'nas'

router = DefaultRouter()
router.register(r'folders', FolderViewSet, basename='nas-folder')
router.register(r'files',   FileViewSet,  basename='nas-file')

urlpatterns = router.urls
