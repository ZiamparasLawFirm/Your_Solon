from django.contrib import admin
from django.urls import path, include
from django.shortcuts import redirect

urlpatterns = [
    # Home → Civil search form
    path("", lambda request: redirect('civil_app:civil_form'), name="home"),

    # Apps
    path("civil/", include("civil_app.urls")),
    path("accounts/", include("django.contrib.auth.urls")),
    path("admin/", admin.site.urls),
]
