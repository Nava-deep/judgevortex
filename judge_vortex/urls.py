from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('mysiteadministration/admin/interface', admin.site.urls),
    path('', include('submissions.urls')),
]