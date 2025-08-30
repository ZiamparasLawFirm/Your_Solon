from typing import Dict, Any
import re

DISPLAY_ORDER = [
    "Υπόθεση",
    "Ημ. Κατάθεσης",
    "Γενικός Αριθμός Κατάθεσης/Έτος",
    "Ειδικός Αριθμός Κατάθεσης/Έτος",
    "Διαδικασία",
    "Αντικείμενο",
    "Είδος",
    "Αριθμός Πινακίου",
    "Αριθμός Απόφασης/Έτος - Είδος Διατακτικού",
    "Αποτέλεσμα Συζήτησης",
    "Δικάσιμος",
]

def _pick_case_title(payload: Any) -> str:
    """
    Try multiple keys so we don't rely on a single one.
    jobs.py will inject client_name/subject/case_title; we also accept a pre-filled 'Υπόθεση'.
    """
    if not isinstance(payload, dict):
        return ""
    for key in ("Υπόθεση", "case_title", "client_name", "subject", "name", "client"):
        v = payload.get(key)
        if v:
            return str(v).strip()
    return ""

def _extract_dikasimos(pinakio_value: str) -> str:
    """
    Extract a date from 'Αριθμός Πινακίου' text and normalize to dd/mm/yyyy.
    Matches dd/mm/yyyy, dd-mm-yyyy, dd.mm.yyyy.
    """
    s = (pinakio_value or "").strip()
    m = re.search(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{4})\b", s)
    if not m:
        return ""
    d, mth, y = m.groups()
    return f"{int(d):02d}/{int(mth):02d}/{y}"

def clean_solon_fields(payload: Any) -> Dict[str, str]:
    # 1) Gather scraped fields
    raw_fields: Dict[str, str] = {}
    if isinstance(payload, dict):
        f = payload.get("fields")
        if isinstance(f, dict):
            raw_fields = {k: (v or "").strip() for k, v in f.items()}
        else:
            raw_fields = {k: (v or "").strip() for k, v in payload.items() if isinstance(v, str)}

    # 2) Compute extras
    case_title = _pick_case_title(payload)
    dikasimos  = _extract_dikasimos(raw_fields.get("Αριθμός Πινακίου", ""))

    # 3) Ordered output
    out: Dict[str, str] = {}
    for key in DISPLAY_ORDER:
        if key == "Υπόθεση":
            out[key] = case_title
        elif key == "Δικάσιμος":
            out[key] = dikasimos
        else:
            out[key] = raw_fields.get(key, "")
    return out

# Back-compat alias used elsewhere
def normalize_payload(payload: Any) -> Dict[str, str]:
    return clean_solon_fields(payload)
