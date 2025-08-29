
import re

CASE_TOKEN_RE = re.compile(r'(?<!\d)(\d{2,8}/\d{4})(?!\d)')

def extract_case_token(text):
    if not isinstance(text, str):
        return text
    t = (text or "").replace("\xa0"," ").strip()
    m = CASE_TOKEN_RE.search(t)
    return m.group(1) if m else t

def _is_ga_key(k: str) -> bool:
    if not isinstance(k, str): return False
    kl = k.casefold()
    return ('γενικός' in kl and 'κατάθεσης' in kl) or 'γακ' in kl or 'γ.α.κ' in kl

def clean_solon_fields(fields: dict):
    if not isinstance(fields, dict): return fields
    out = {}
    for k, v in fields.items():
        out[k] = extract_case_token(v) if _is_ga_key(k) else v
    return out

def normalize_payload(payload: dict):
    if not isinstance(payload, dict): return payload
    p = dict(payload)
    if isinstance(p.get('fields'), dict):
        p['fields'] = clean_solon_fields(p['fields'])
    return p
