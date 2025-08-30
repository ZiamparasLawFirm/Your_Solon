from typing import Dict, Any

DISPLAY_ORDER = [
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

def clean_solon_fields(payload: Any) -> Dict[str, str]:
    """
    Accepts the scraper payload and returns a plain dict with the above greek keys.
    Missing keys are returned as empty strings to keep the UI stable.
    """
    fields = {}
    if isinstance(payload, dict):
        f = payload.get("fields")
        if isinstance(f, dict):
            fields = {k: (v or "").strip() for k, v in f.items()}
        else:
            # fallback: try to treat the whole payload as already-normalized
            fields = {k: (v or "").strip() for k, v in payload.items() if isinstance(v, str)}

    # Ensure all keys exist (UI expects them)
    return {k: fields.get(k, "") for k in DISPLAY_ORDER}

# Back-compat alias some code paths might import
def normalize_payload(payload: Any) -> Dict[str, str]:
    return clean_solon_fields(payload)
