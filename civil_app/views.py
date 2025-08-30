from __future__ import annotations
import json
from typing import List, Tuple, Dict, Any
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from .models import CivilSearchJob, Court
from .jobs import run_civil_job

DISPLAY_ORDER: List[str] = [
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
def civil_form(request: HttpRequest) -> HttpResponse:
    courts = Court.objects.order_by("name")
    if request.method == "POST":
        client_name = request.POST.get("client_name", "").strip()
        court_id = request.POST.get("court", "").strip()
        gak_number = request.POST.get("gak_number", "").strip()
        gak_year = request.POST.get("gak_year", "").strip()

        if not court_id:
            return render(request, "civil_app/civil_form.html",
                          {"courts": courts, "error": "Επιλέξτε δικαστήριο.",
                           "prefill": {"client_name": client_name, "gak_number": gak_number, "gak_year": gak_year}})

        court = get_object_or_404(Court, id=court_id)
        job = CivilSearchJob.objects.create(
            user=request.user,
            client_name=client_name,
            court=court,
            gak_number=gak_number,
            gak_year=gak_year,
            status="queued",
        )
        # Run synchronously in dev to avoid getting stuck on waiting
        run_civil_job(job.id)
        return redirect("civil_app:job_status_page", job_id=job.id)

    return render(request, "civil_app/civil_form.html", {"courts": courts})

@login_required
def job_status_page(request: HttpRequest, job_id: int) -> HttpResponse:
    job = get_object_or_404(CivilSearchJob, id=job_id, user=request.user)
    return render(request, "civil_app/job_status.html", {"job": job})

@login_required
def job_status_api(request: HttpRequest, job_id: int) -> HttpResponse:
    job = get_object_or_404(CivilSearchJob, id=job_id, user=request.user)

    data: Dict[str, Any] = {}
    if getattr(job, "snapshot_id", None):
        data = getattr(job.snapshot, "data_json", {}) or {}

    normalized: Dict[str, Any] = data.get("normalized", data) or {}
    raw_payload: Any = data.get("raw")

    display_fields: List[Tuple[str, str]] = []
    if isinstance(normalized, dict):
        display_fields = [(label, (normalized.get(label) or "")) for label in DISPLAY_ORDER]

    debug = ("debug" in request.GET)
    raw_pretty = None
    if debug and raw_payload is not None:
        try:
            raw_pretty = json.dumps(raw_payload, ensure_ascii=False, indent=2)
        except Exception:
            raw_pretty = str(raw_payload)

    return render(
        request,
        "civil_app/status_fragment.html",
        {
            "job": job,
            "display_fields": display_fields,
            "has_raw": raw_payload is not None,
            "raw_pretty": raw_pretty,
        },
    )

from django.contrib.auth.decorators import login_required

@login_required
def debug_direct_scrape(request):
    """
    TEMP endpoint: call the scraper directly to compare results under Django.
    GET params: court_id, gak_number, gak_year
    Example:
      /civil/debug/scrape/?court_id=50&gak_number=70927&gak_year=2025
    """
    from django.http import JsonResponse
    from .solon_scraper_adf import scrape_solon_civil_adf
    from .models import Court

    cid  = request.GET.get("court_id")
    num  = request.GET.get("gak_number")
    year = request.GET.get("gak_year")
    try:
        label = Court.objects.get(id=int(cid)).name
    except Exception:
        label = str(cid or "")
    data = scrape_solon_civil_adf(label, str(num or ""), int(str(year or "0")))
    return JsonResponse(data, safe=False)
