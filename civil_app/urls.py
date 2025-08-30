# -*- coding: utf-8 -*-
from django.urls import path
from . import views

app_name = "civil_app"

urlpatterns = [
    path("", views.civil_form, name="civil_form"),
    path("status/<int:job_id>/", views.job_status_page, name="job_status_page"),
    path("status/<int:job_id>/fragment/", views.job_status_api, name="job_status_api"),
    path("debug/scrape/", views.debug_direct_scrape, name="debug_direct_scrape"),
]
