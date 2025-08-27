"""
Project URL configuration.

- Admin at /admin/
- Built-in auth views (login, logout, password reset) at /accounts/
- Our civil_app routes at /civil/
"""

from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("django.contrib.auth.urls")),  # login/logout/password reset
    path("civil/", include("civil_app.urls")),               # our app
]

