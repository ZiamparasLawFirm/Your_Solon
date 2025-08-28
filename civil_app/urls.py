# civil_app/urls.py
from django.urls import path
from . import views

app_name = "civil_app"

urlpatterns = [
    # main form (Αστικά)
    path("", views.civil_form, name="civil_form"),

    # status page + fragment poll
    path("status/<int:job_id>/", views.job_status_page, name="job_status_page"),
    path("status/<int:job_id>/fragment/", views.job_status_api, name="job_status_api"),

    # navbar placeholders
    path("home/", views.home, name="home"),
    path("civil-offsolon/", views.civil_offsolon, name="civil_offsolon"),
    path("admin-cases/", views.admin_cases, name="admin_cases"),
    path("calendar/", views.calendar, name="calendar"),
    path("penal/", views.penal, name="penal"),
]
