from __future__ import annotations
import re
from typing import Any, Dict, List, Tuple

ORDER = [
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

_date = re.compile(r'^\s*\d{1,2}/\d{1,2}/\d{4}\s*$')
_numyear = re.compile(r'\d+/\d{4}')

def _pairs_from_payload(payload: Any) -> List[Tuple[str,str]]:
    # Prefer payload['fields'] if present; keep ORDER
    if isinstance(payload, dict):
        fields = payload.get("fields")
        if isinstance(fields, dict):
            return [(lab, str(fields.get(lab, "")).strip()) for lab in ORDER]
        if isinstance(fields, list):
            out=[]
            for kv in fields:
                if isinstance(kv,(list,tuple)) and len(kv)==2:
                    out.append((str(kv[0]).strip(), str(kv[1]).strip()))
            return out
        # fallback: top-level dict
        return [(lab, str(payload.get(lab, "")).strip()) for lab in ORDER]
    return []

def _shift_if_needed(pairs: List[Tuple[str,str]]) -> List[Tuple[str,str]]:
    if not pairs: return pairs
    labels = [l for l,_ in pairs]
    values = [v for _,v in pairs]
    # If "Ημ. Κατάθεσης" isn't a date but the NEXT is, rotate values left by 1.
    if len(values) >= 2 and not _date.match(values[0]) and _date.match(values[1]):
        values = values[1:] + [""]
        return list(zip(labels, values))
    return pairs

def _fix_gen(v: str) -> str:
    if not v: return v
    m = _numyear.findall(v)
    return m[0] if m else v.strip()

def normalize_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    pairs = _pairs_from_payload(payload)
    pairs = _shift_if_needed(pairs)

    fixed: List[Tuple[str,str]] = []
    for label, value in pairs:
        v = (value or "").strip()
        if label == "Γενικός Αριθμός Κατάθεσης/Έτος":
            v = _fix_gen(v)
        fixed.append((label, v))

    # drop "Απόφαση" entirely if present
    fixed = [(l,v) for (l,v) in fixed if l != "Απόφαση"]

    # Rebuild payload.fields dict with corrected values; preserve other top-level keys.
    base = dict(payload) if isinstance(payload, dict) else {}
    fields = base.get("fields", {})
    if not isinstance(fields, dict):
        fields = {}
    for lab, val in fixed:
        fields[lab] = val
    base["fields"] = fields
    return base
