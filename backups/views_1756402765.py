# civil_app/views.py
from __future__ import annotations

import re
from .jobs import start_civil_job
from typing import Dict, List, Tuple

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse

from .models import CivilSearchJob, CaseSnapshot, Court
from civil_app.jobs import start_civil_job
# --- MySolon display order (left column in your screenshot) ---
MYSOLON_FIELDS_ORDER: List[str] = [
    "Ημ. Κατάθεσης",
    "Γενικός Αριθμός Κατάθεσης/Έτος",
    "Ειδικός Αριθμός Κατάθεσης/Έτος",
    "Διαδικασία",
    "Αντικείμενο",
    "Είδος",
    "Αριθμός Πινακίου",
    "Αριθμός Απόφασης/Έτος - Είδος Διατακτικού",
    "Αποτέλεσμα Συζήτησης",
]

_date_rx = re.compile(r"^\d{2}/\d{2}/\d{4}$")

def _tidy_and_order_fields(fields: Dict[str, str]) -> List[Tuple[str, str]]:
    """
    1) Fix common ADF swap: if 'Ημ. Κατάθεσης' is NOT a date but
       'Γενικός ...' IS a date -> swap their values.
    2) Return a list of (label, value) sorted in MySolon order,
       with any extra fields appended at the end.
    """
    if not fields:
        return []

    k_date = next((k for k in fields.keys() if k.replace(" ", "") in ("Ημ.Κατάθεσης", "Ημ.Κατάθεσης")), "Ημ. Κατάθεσης")
    # Normalize possible key variants to match our order label
    # If the exact key "Ημ. Κατάθεσης" exists use that, else keep k_date.
    if "Ημ. Κατάθεσης" in fields:
        k_date = "Ημ. Κατάθεσης"

    k_gen = "Γενικός Αριθμός Κατάθεσης/Έτος"

    if k_date in fields and k_gen in fields:
        v_date = (fields.get(k_date) or "").strip()
        v_gen  = (fields.get(k_gen) or "").strip()
        if not _date_rx.match(v_date) and _date_rx.match(v_gen):
            fields[k_date], fields[k_gen] = v_gen, v_date

    ordered: List[Tuple[str, str]] = []
    seen = set()
    for label in MYSOLON_FIELDS_ORDER:
        if label in fields:
            ordered.append((label, fields[label]))
            seen.add(label)

    # Append any remaining fields we didn’t explicitly order
    for k, v in fields.items():
        if k not in seen:
            ordered.append((k, v))

    return ordered

@login_required
def civil_form(request: HttpRequest) -> HttpResponse:
    courts = Court.objects.filter(is_active=True).order_by("name")
    if request.method == "POST":
        client_name = request.POST.get("client_name", "").strip()
        court_id    = request.POST.get("court", "").strip()
        gak_number  = request.POST.get("gak_number", "").strip()
        gak_year    = request.POST.get("gak_year", "").strip()

        if not court_id:
            messages.error(request, "Παρακαλώ επιλέξτε Δικαστήριο.")
            return render(request, "civil_app/civil_form.html", {"courts": courts, "form_error": "Παρακαλώ επιλέξτε Δικαστήριο.", "prefill": {"client_name": client_name, "gak_number": gak_number, "gak_year": gak_year}})
        court = get_object_or_404(Court, id=court_id)
        job = CivilSearchJob.objects.create(
            user=request.user,
            client_name=client_name,
            court=court,
            gak_number=gak_number,
            gak_year=gak_year,
            status="queued",
        )
        start_civil_job(job.id)
        # fire async (tasks.py respects CELERY_TASK_ALWAYS_EAGER=True in dev)
        return redirect("civil_app:job_status_page", job_id=job.id)

    return render(request, "civil_app/civil_form.html", {"courts": courts})

@login_required
def job_status_page(request: HttpRequest, job_id: int) -> HttpResponse:
    job = get_object_or_404(CivilSearchJob, id=job_id, user=request.user)
    # Page with HTMX that polls job_status_api
    return render(request, "civil_app/job_status.html", {"job": job})

@login_required
def job_status_api(request: HttpRequest, job_id: int) -> HttpResponse:
    """
    Returns the HTML fragment with the current job status. HTMX swaps into the page.
    """
    job = get_object_or_404(CivilSearchJob, id=job_id, user=request.user)

    ctx = {"job": job, "ordered_fields": None, "data": None, "error": None}
    if job.status in ("done", "failed"):
        snap = CaseSnapshot.objects.filter(job=job).order_by("-created_at").first()
        payload = snap.data if snap else None
        ctx["data"] = payload

        if payload and isinstance(payload, dict):
            fields = (payload.get("fields") or {}) if isinstance(payload.get("fields"), dict) else {}
            ctx["ordered_fields"] = _tidy_and_order_fields(fields)

        if job.status == "failed":
            ctx["error"] = job.error_message or "Σφάλμα αναζήτησης."

    return render(request, "civil_app/_status_fragment.html", ctx)

# ----------------- Navbar placeholders -----------------

@login_required
def home(request: HttpRequest) -> HttpResponse:
    return render(request, "civil_app/under_construction.html", {"title": "Αρχική"})

@login_required
def civil_offsolon(request: HttpRequest) -> HttpResponse:
    return render(request, "civil_app/under_construction.html", {"title": "Αστικά (Εκτός Σόλων)"})

@login_required
def admin_cases(request: HttpRequest) -> HttpResponse:
    return render(request, "civil_app/under_construction.html", {"title": "Διοικητικά"})

@login_required
def calendar(request: HttpRequest) -> HttpResponse:
    return render(request, "civil_app/under_construction.html", {"title": "Ημερολόγιο"})

@login_required
def penal(request: HttpRequest) -> HttpResponse:
    return render(request, "civil_app/under_construction.html", {"title": "Πιν. Ποινικών"})


# --- override job_status_api to send HX-Trigger & ordered fields ---
from django.http import HttpResponse  # ensure available

FIELD_ORDER = [
    "Ημ. Κατάθεσης",
    "Γενικός Αριθμός Κατάθεσης/Έτος",
    "Ειδικός Αριθμός Κατάθεσης/Έτος",
    "Διαδικασία",
    "Αντικείμενο",
    "Είδος",
    "Αριθμός Πινακίου",
    "Αριθμός Απόφασης/Έτος - Είδος Διατακτικού",
    "Αποτέλεσμα Συζήτησης",
]

@login_required
def job_status_api(request: HttpRequest, job_id: int) -> HttpResponse:
    job = get_object_or_404(CivilSearchJob, id=job_id, user=request.user)
    ordered = []
    header = {}
    if getattr(job, "snapshot_id", None):
        data = job.snapshot.data_json or {}
        header = {
            "Δικαστήριο": data.get("Κατάστημα", ""),
            "ΓΑΚ": data.get("ΓΑΚ", ""),
            "Απόφαση": data.get("Απόφαση", ""),
        }
        fields = data.get("fields") or {}
        for label in FIELD_ORDER:
            if label in fields:
                ordered.append((label, fields.get(label)))
    resp = render(request, "civil_app/status_fragment.html",
                  {"job": job, "ordered": ordered, "header": header})
    if job.status in ("done", "failed"):
        resp["HX-Trigger"] = "stopPolling"
    return resp
