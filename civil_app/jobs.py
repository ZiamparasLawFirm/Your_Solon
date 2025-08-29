from threading import Thread
import re
from .normalizers import normalize_payload, clean_solon_fields, clean_solon_fields
from .normalizers import normalize_payload, clean_solon_fields, normalize_payload

from .models import Case, CaseSnapshot, CivilSearchJob
from .normalize import normalize_payload
from .solon_scraper_adf import scrape_solon_civil_adf


def _run_job(job_id: int):
    job = CivilSearchJob.objects.select_related("court").get(id=job_id)
    job.status = "running"
    job.error = ""
    job.save()

    try:
        court_label = (job.court.name if getattr(job, "court_id", None) else "") or getattr(job, "court_name", "") or ""
        res = scrape_solon_civil_adf(court_label, str(job.gak_number), int(job.gak_year))

        case_title = f"{res.get('Κατάστημα') or court_label} — ΓΑΚ {job.gak_number}/{job.gak_year}"

        if hasattr(job, "case"):
            job.case = Case.objects.get_or_create(court=job.court, gak_number=job.gak_number, gak_year=job.gak_year)[0]
        if hasattr(job, "case_string"):
            job.case_string = case_title
        if hasattr(job, "snapshot"):
            snapshot = CaseSnapshot.objects.create(case=job.case, data_json=res)
            job.snapshot = snapshot
        if hasattr(job, "result"):
            job.result = res

        job.status = "done"
        job.save()
    except Exception as e:
        job.status = "failed"
        job.error = str(e)
        job.save()


def run_civil_job(job_id: int):
    """Run synchronously (useful for debugging)."""
    _run_job(job_id)


def start_civil_job(job_id: int):
    """Fire-and-forget background thread."""
    t = Thread(target=_run_job, args=(job_id,), daemon=True)
    t.start()
    return t


def _normalize_payload_for_general_number(payload):
    """
    Keep only the true value for 'Γενικός Αριθμός Κατάθεσης/Έτος'
    by extracting the first NNNNN/YYYY pattern from whatever the scraper
    returned (no hardcoding; purely regex-based).
    """
    try:
        fields = payload.get('fields') or {}
        key = "Γενικός Αριθμός Κατάθεσης/Έτος"
        val = fields.get(key)
        if isinstance(val, str):
            m = re.search(r"\b\d{1,7}/\d{4}\b", val)
            if m:
                fields[key] = m.group(0)
        payload['fields'] = clean_solon_fields(fields)
    except Exception:
        # Best-effort; don't block the pipeline
        pass
    return payload


def _normalize_fields_strict(payload):
    """
    Fix overlong values by keeping only the true number for
    'Γενικός Αριθμός Κατάθεσης/Έτος' (first NNNNN/YYYY found).
    No hardcoding of concrete values; regex-only.
    """
    try:
        fields = payload.get('fields') or {}
        # Be robust to label variants
        candidates = [k for k in fields.keys()
                      if ("Γενικός" in k and "Κατάθεσης" in k)
                      or ("ΓΑΚ" in k)]
        for key in candidates:
            val = fields.get(key)
            if isinstance(val, str):
                m = re.search(r"\b\d{1,7}/\d{4}\b", val)
                if m:
                    fields[key] = m.group(0)
        payload['fields'] = clean_solon_fields(fields)
    except Exception:
        pass
    return payload


def _normalize_general_number(payload):
    """
    Keep ONLY the real number (NNNNN/YYYY) for
    'Γενικός Αριθμός Κατάθεσης/Έτος' (or labels containing 'Γενικός'/'ΓΑΚ').
    Avoid picking dates like 24/03/2025 by requiring 4–8 digits before '/'.
    """
    try:
        fields = (payload.get('fields') or {}).copy()
        target_key = None
        for k in fields.keys():
            if ('Γενικός' in k and 'Κατάθεσης' in k) or ('ΓΑΚ' in k):
                target_key = k
                break
        if target_key:
            v = fields.get(target_key)
            if isinstance(v, str):
                m = re.search(r'(?<!\d)(\d{4,8}/\d{4})(?!\d)', v)
                if not m:
                    m = re.search(r'ΓΑΚ\D*(\d{4,8}/\d{4})', v, flags=re.I)
                if not m:
                    m = re.search(r'\b\d+/\d{4}\b', v)  # last resort
                if m:
                    fields[target_key] = m.group(1).strip()
        payload = dict(payload)
        payload = _fix_only_ga_field(payload)
        payload = _normalize_case_numbers(payload)
        payload = _normalize_general_number(payload)
        payload['fields'] = clean_solon_fields(fields)
        return payload
    except Exception:
        return payload


def _normalize_case_numbers(payload):
    """
    Keep ONLY the real case number (NNNNN/YYYY) for:
      - 'Γενικός Αριθμός Κατάθεσης/Έτος' (ΓΑΚ)
      - 'Ειδικός Αριθμός Κατάθεσης/Έτος'
    If a long string contains multiple tokens, keep the FIRST token only.
    """
    try:
        fields = dict((payload.get('fields') or {}))
    except Exception:
        return payload

    def _strip_first_num(v):
        if not isinstance(v, str):
            return v
        v = v.replace("\xa0", " ").strip()
        # Prefer 4–8 digits / 4 digits (avoid dates like 24/03/2025)
        m = re.search(r'(?<!\d)(\d{4,8}/\d{4})(?!\d)', v)
        if m:
            return m.group(1)
        # Fallback: patterns like 'ΓΑΚ 70927/2025'
        m = re.search(r'(?:ΓΑΚ|Γ\.?\s*Α\.?\s*Κ\.?)\D*(\d{4,8}/\d{4})', v, flags=re.I)
        if m:
            return m.group(1)
        # Last resort
        m = re.search(r'\b(\d+/\d{4})\b', v)
        return m.group(1) if m else v

    new_fields = {}
    for k, v in (fields.items()):
        kl = k.casefold()
        if ('γενικός' in kl and 'κατάθεσης' in kl) or re.search(r'γ\.?\s*α\.?\s*κ', kl, flags=re.I):
            new_fields[k] = _strip_first_num(v)
        elif ('ειδικός' in kl and 'κατάθεσης' in kl):
            new_fields[k] = _strip_first_num(v)
        else:
            new_fields[k] = v

    out = dict(payload)
    out['fields'] = new_fields
    return out


def _fix_only_ga_field(payload):
    # Keep ONLY the first real case token NNNNN/YYYY for ΓΑΚ / Γενικός Αριθμός Κατάθεσης/Έτος
    try:
        fields = dict(payload.get('fields') or {})
    except Exception:
        return payload

    def only_case_token(val):
        if not isinstance(val, str):
            return val
        val = val.replace("\xa0", " ").strip()
        # prefer 4–8 digits / 4 digits (e.g. 70927/2025). Won't match dates like 24/03/2025.
        m = re.search(r'(?<!\d)(\d{4,8}/\d{4})(?!\d)', val)
        if m:
            return m.group(1)
        # fallback when "ΓΑΚ" text precedes the token
        m = re.search(r'(?:ΓΑΚ|Γ\.?\s*Α\.?\s*Κ\.?)\D*(\d{4,8}/\d{4})', val, flags=re.I)
        return m.group(1) if m else val

    new_fields = {}
    for k, v in (fields.items()):
        kl = k.casefold()
        if ('γενικός' in kl and 'κατάθεσης' in kl) or 'γ.α.κ' in kl or 'γακ' in kl:
            new_fields[k] = only_case_token(v)
        else:
            new_fields[k] = v

    out = dict(payload)
    out['fields'] = new_fields
    return out
