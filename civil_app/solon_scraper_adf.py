# -*- coding: utf-8 -*-
from __future__ import annotations
import os, re, unicodedata
from typing import Dict, Any, List, Tuple
from playwright.sync_api import sync_playwright, Page
from .normalizers import clean_solon_fields
from .normalizers import clean_solon_fields, normalize_payload

URL = "https://extapps.solon.gov.gr/mojwp/faces/TrackLdoPublic"

# Oracle ADF selectors (escape :)
SEL_KATASTIMA   = "#courtOfficeOC\\:\\:content"
SEL_GAK_NUMBER  = "#it1\\:\\:content"
SEL_GAK_YEAR    = "#it2\\:\\:content"
SEL_SEARCH_BTN  = "#ldoSearch a"

# Grid
SEL_GRID        = "#pc1\\:ldoTable"
SEL_GRID_DB     = "#pc1\\:ldoTable\\:\\:db"
SEL_GRID_HDR    = "#pc1\\:ldoTable\\:\\:hdr"
SEL_GRID_SPIN   = "#pc1\\:ldoTable\\:\\:sm"

DEFAULT_TIMEOUT = 30_000
RESULT_TIMEOUT  = int(os.getenv("RESULT_TIMEOUT_MS", "60000"))

FALLBACK_HEADERS = [
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

def _n(s:str)->str:
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(ch for ch in s if unicodedata.category(ch)!="Mn")
    s = s.replace("\u00a0"," ").replace("\u200b","")
    s = re.sub(r"\s+"," ", s)
    return s.strip()

def _nk(s:str)->str: return _n(s).lower()

def _accept_cookies(p:Page):
    for label in ("Αποδοχή","Αποδέχομαι","Συμφωνώ","Accept","Accept all","OK","Ok"):
        try: p.get_by_role("button", name=label).first.click(timeout=800); p.wait_for_timeout(120); return
        except Exception: pass
        try: p.get_by_text(label).first.click(timeout=800); p.wait_for_timeout(120); return
        except Exception: pass

def _wait_clickable(p:Page, sel:str, t=5000):
    p.locator(sel).scroll_into_view_if_needed()
    p.wait_for_function("""
      (sel)=>{
        const el=document.querySelector(sel); if(!el) return false;
        const r=el.getBoundingClientRect(); const cx=r.left+r.width/2, cy=r.top+r.height/2;
        const top=document.elementFromPoint(cx,cy);
        return !!top && (top===el || el.contains(top));
      }""", arg=sel, timeout=t)

def _set_input(p:Page, sel:str, val:str):
    try: _wait_clickable(p, sel)
    except Exception: pass
    try:
        p.evaluate("""(a)=>{
          const el=document.querySelector(a.sel); if(!el) return false;
          el.focus(); el.value='';
          el.dispatchEvent(new Event('input',{bubbles:true}));
          el.value=String(a.val??'');
          el.dispatchEvent(new Event('input',{bubbles:true}));
          el.dispatchEvent(new Event('change',{bubbles:true}));
          return true;
        }""", {"sel": sel, "val": str(val)})
        p.wait_for_timeout(70)
    except Exception:
        p.locator(sel).fill(str(val))

def _spin(p:Page):
    try: p.wait_for_selector(SEL_GRID_SPIN, state="visible", timeout=2000)
    except Exception: pass
    try: p.wait_for_selector(SEL_GRID_SPIN, state="hidden", timeout=RESULT_TIMEOUT)
    except Exception: pass

def _wait_table_ready(p:Page, timeout=RESULT_TIMEOUT):
    p.wait_for_selector(SEL_GRID, state="visible", timeout=DEFAULT_TIMEOUT)
    p.wait_for_function("""
      (dbSel)=>{
        const db=document.querySelector(dbSel); if(!db) return false;
        const txt=(db.textContent||'').trim();
        return txt.includes("Δεν υπάρχουν δεδομένα") || !!db.querySelector("td,[role='gridcell']");
      }""", arg=SEL_GRID_DB, timeout=timeout)

def _click_search(p:Page):
    try: _wait_clickable(p, SEL_SEARCH_BTN)
    except Exception: pass
    try: p.locator(SEL_SEARCH_BTN).first.click(timeout=2000); return
    except Exception: pass
    try: p.evaluate("(s)=>{const el=document.querySelector(s); if(el) el.click();}", SEL_SEARCH_BTN)
    except Exception: pass

def _extract_header_cmap(p:Page)->List[Tuple[int,str]]:
    # Prefer header ids ending with :cN (ADF)
    cmap = p.evaluate(r"""
      (hdrSel)=>{
        const hdr=document.querySelector(hdrSel);
        const out=[];
        const norm=s=>(s||'').toString().replace(/\u00A0/g,' ').replace(/\s+/g,' ').trim();
        if(!hdr) return out;
        const cand = Array.from(hdr.querySelectorAll("*")).filter(e=>/:c\d+$/.test(e.id||""));
        const seen=new Set();
        for (const el of cand){
          const m=(el.id||"").match(/:c(\d+)$/); if(!m) continue;
          const idx=Number(m[1]);
          const txt=norm(el.innerText||el.getAttribute("title")||"");
          if(!txt || seen.has(idx)) continue;
          seen.add(idx);
          out.push([idx, txt]);
        }
        out.sort((a,b)=>a[0]-b[0]);
        return out;
      }
    """, SEL_GRID_HDR) or []
    if cmap: return cmap

    # Fallback ARIA headers with aria-colindex
    cmap = p.evaluate(r"""
      (gridSel)=>{
        const grid=document.querySelector(gridSel);
        const out=[];
        const norm=s=>(s||'').toString().replace(/\u00A0/g,' ').replace(/\s+/g,' ').trim();
        if(!grid) return out;
        const cols=Array.from(grid.querySelectorAll('[role="columnheader"]'));
        for (const col of cols){
          const idx = Number(col.getAttribute("aria-colindex")||"0")-1;
          const txt = norm(col.innerText||col.getAttribute("title")||"");
          if(Number.isFinite(idx) && txt) out.push([idx, txt]);
        }
        out.sort((a,b)=>a[0]-b[0]);
        return out;
      }
    """, SEL_GRID) or []
    if cmap: return cmap

    # Last resort: known positions
    return list(enumerate(FALLBACK_HEADERS))

def _extract_row_cmap(p:Page, gak_num:str, gak_year:str)->List[Tuple[int,str]]:
    # Return [(cIndex, value), ...] from the matched row
    return p.evaluate(r"""
      (args)=>{
        const {dbSel, num, year} = args;
        const db=document.querySelector(dbSel);
        if(!db) return [];
        const norm=s=>(s||'').toString().replace(/\u00A0/g,' ').replace(/\s+/g,' ').trim();
        const esc=s=>s.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
        const nn=norm(num), ny=norm(year);
        const rx = new RegExp('^\\s*'+esc(nn)+'\\s*/\\s*'+esc(ny)+'\\s*$');

        const rows = Array.from(db.querySelectorAll("tr,[role='row']"));
        for (const row of rows){
          const cells = Array.from(row.querySelectorAll("td,[role='gridcell']"));
          if(!cells.length) continue;

          const texts = cells.map(td=>norm(td.innerText));
          const hasNum  = texts.some(t=>t===nn);
          const hasYear = texts.some(t=>t===ny);
          const hasComb = texts.some(t=>rx.test(t));
          if (!((hasNum&&hasYear) || hasComb)) continue;

          const out=[];
          for (let i=0;i<cells.length;i++){
            const td=cells[i];
            let cIndex=null;

            // Prefer :cN on cell id
            const m=(td.id||"").match(/:c(\d+)$/);
            if(m) cIndex=Number(m[1]);

            // Else via headers attr -> header id -> :cN
            if(cIndex===null){
              const hids=(td.getAttribute("headers")||"").trim().split(/\s+/).filter(Boolean);
              for (const hid of hids){
                const h=document.getElementById(hid);
                if(!h) continue;
                const mh=(h.id||"").match(/:c(\d+)$/);
                if(mh){ cIndex=Number(mh[1]); break; }
              }
            }

            // Fallback: visual order
            if(cIndex===null) cIndex = i;

            const val = norm(td.innerText);
            out.push([cIndex, val]);
          }

          // Deduplicate by cIndex, keep first
          const seen=new Set(), uniq=[];
          for (const [c,v] of out){
            if(seen.has(c)) continue;
            seen.add(c); uniq.push([c,v]);
          }
          uniq.sort((a,b)=>a[0]-b[0]);
          return uniq;
        }
        return [];
      }
    """, {"dbSel": SEL_GRID_DB, "num": str(gak_num), "year": str(gak_year)})


import re
def _tidy_fields(fields: Dict[str,str]) -> Dict[str,str]:
    """Fix common ADF header↔value misalignments safely.
    - Ensure 'Ημ. Κατάθεσης' is a date (dd/mm/yyyy); if not, swap with 'Γενικός ...'
    """
    date_rx = re.compile(r"^\d{2}/\d{2}/\d{4}$")
    k_date = "Ημ. Κατάθεσης"
    k_gen  = "Γενικός Αριθμός Κατάθεσης/Έτος"
    if k_date in fields and k_gen in fields:
        v_date = (fields.get(k_date) or "").strip()
        v_gen  = (fields.get(k_gen) or "").strip()
        if not date_rx.match(v_date) and date_rx.match(v_gen):
            fields[k_date], fields[k_gen] = v_gen, v_date
    return fields

def _normalize_fields(fields):
    import re as _re
    # swap date if Solon mislabeled them
    d=(fields.get('Γενικός Αριθμός Κατάθεσης/Έτος') or '').strip()
    h=(fields.get('Ημ. Κατάθεσης') or '').strip()
    if _re.fullmatch(r'\d{2}/\d{2}/\d{4}', d) and not _re.fullmatch(r'\d{2}/\d{2}/\d{4}', h):
        fields['Ημ. Κατάθεσης'], fields['Γενικός Αριθμός Κατάθεσης/Έτος'] = d, h
    # fix Είδος vs Αριθμός Πινακίου if flipped
    e=(fields.get('Είδος') or '')
    ap=(fields.get('Αριθμός Πινακίου') or '')
    if ('ΑΙΤΗΣ' in e.upper() and ap) and ('ΡΥΘΜΙΣ' in ap.upper() or 'ΚΑΤΑΣΤ' in ap.upper()):
        fields['Είδος'], fields['Αριθμός Πινακίου'] = ap, e
    # keep only the first dd/mm/yyyy in Ημ. Κατάθεσης
    h2=(fields.get('Ημ. Κατάθεσης') or '')
    m=_re.search(r'(\d{2}/\d{2}/\d{4})', h2)
    if m:
        fields['Ημ. Κατάθεσης']=m.group(1)
    return fields

def scrape_solon_civil_adf(court_label: str, gak_number: str, year: int) -> Dict[str, Any]:

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = browser.new_context(locale="el-GR", viewport={"width":1500,"height":950})
        page = ctx.new_page()
        page.set_default_timeout(DEFAULT_TIMEOUT)

        page.goto(URL, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_load_state("networkidle")
        _accept_cookies(page)

        # Resolve court from dropdown
        options = page.locator(f"{SEL_KATASTIMA} option")
        texts   = options.all_text_contents()
        values  = options.evaluate_all("els => els.map(e => e.value)")
        want = _nk(court_label)
        court_value=None
        for t,v in zip(texts, values):
            if _nk(t) == want or (want and want in _nk(t)):
                court_value=v; break
        if not court_value:
            ctx.close(); browser.close()
            raise RuntimeError("Δεν βρέθηκε το ζητούμενο δικαστήριο στο dropdown.")

        cur = page.locator(SEL_KATASTIMA).evaluate("el => el.value")
        if cur != court_value:
            page.select_option(SEL_KATASTIMA, value=court_value)
            page.wait_for_timeout(80)

        _set_input(page, SEL_GAK_NUMBER, str(gak_number).strip())
        _set_input(page, SEL_GAK_YEAR,   str(year).strip())
        _click_search(page)
        _spin(page)
        _wait_table_ready(page, timeout=RESULT_TIMEOUT)
        _spin(page)

        header_cmap = _extract_header_cmap(page)                     # [(cIndex, label), ...]
        row_cmap    = _extract_row_cmap(page, str(gak_number), str(year))  # [(cIndex, value), ...]

        ctx.close(); browser.close()

    # Build label -> value using cIndex join
    idx_to_label = {c:_n(lbl) for c,lbl in header_cmap if _n(lbl)}
    fields: Dict[str,str] = {}
    for c,val in row_cmap:
        lbl = idx_to_label.get(c)
        if lbl:
            fields[lbl] = _n(val)

    # Tidy known misalignments
    fields = clean_solon_fields(_tidy_fields)(fields)

    # If still empty, fallback positional mapping
    if not fields and row_cmap:
        for i,(c,val) in enumerate(row_cmap):
            if i < len(FALLBACK_HEADERS):
                fields[FALLBACK_HEADERS[i]] = _n(val)

    # Try pull decision (after tidy)
    decision = ""
    for k,v in fields.items():
        if "απόφασης" in _nk(k):
            decision = v; break

    return {
        "Κατάστημα": court_label,
        "ΓΑΚ": f"{gak_number}/{year}",
        "Απόφαση": decision,
        "fields": _normalize_fields(fields),
    }


# --- Post-process normalization for SOLON fields ---
def _postprocess_fields(fields: dict) -> dict:
    """
    Fix common SOLON misalignment where each field (from #2 onward) contains the
    previous field's value, and normalize the date for 'Ημ. Κατάθεσης'.
    """
    import re as _re
    order = [
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
    d = dict(fields or {})

    # Keep only the date in 'Ημ. Κατάθεσης' (dd/mm/yyyy if present)
    def _only_date(text):
        m = _re.search(r'(\d{1,2}/\d{1,2}/\d{4})', str(text or ""))
        return m.group(1) if m else (text or "")
    d["Ημ. Κατάθεσης"] = _only_date(d.get("Ημ. Κατάθεσης", ""))

    # Detect classic shift: 2nd field looks like a date -> values likely shifted by one
    looks_like_date = bool(_re.fullmatch(r'\d{1,2}/\d{1,2}/\d{4}', str(d.get(order[1], ""))))
    if looks_like_date:
        fixed = {}
        fixed[order[0]] = d.get(order[0], "")
        for i in range(1, len(order)-1):
            fixed[order[i]] = d.get(order[i+1], "")
        # last field recovery (best effort)
        last_guess = str(d.get(order[-1], "")) or "-"
        fixed[order[-1]] = last_guess
        d = fixed

    return d


def _postprocess_fields(fields: dict) -> dict:
    """
    Normalize SOLON fields when values are shifted down by one (classic case)
    and clean up specific values (dates, trailing 'ΣΥΖΗΤΗΘΗΚΕ', etc.).
    """
    import re as _re
    order = [
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
    d = dict(fields or {})

    def _only_date(text):
        m = _re.search(r'(\d{1,2}/\d{1,2}/\d{4})', str(text or ""))
        return m.group(1) if m else (text or "")

    def _gak_pat(x):
        return bool(_re.fullmatch(r'\d+\/\d{4}', str(x or "").strip()))

    # 1) Always fix date-only for first field
    d[order[0]] = _only_date(d.get(order[0], ""))

    # 2) Detect misalignment: if the "Ειδικός" or "Διαδικασία" looks like NNNNN/YYYY
    misaligned = _gak_pat(d.get(order[2])) or _gak_pat(d.get(order[3]))

    if misaligned:
        fixed = {}

        # Keep the cleaned date
        fixed[order[0]] = d.get(order[0], "")

        # "Γενικός" → first NNNNN/YYYY we can find (prefer in original "Γενικός",
        # else take from old "Ειδικός")
        g_big = str(d.get(order[1], "") or "")
        m = _re.search(r'\d+\/\d{4}', g_big)
        fixed[order[1]] = (m.group(0) if m else str(d.get(order[2], "")).strip())

        # Shift the rest up by one: field[i] <- old field[i+1]
        for i in range(2, len(order) - 1):
            fixed[order[i]] = str(d.get(order[i + 1], "")).strip()

        # For last field, try to salvage from the tail of original "Γενικός"
        tail = g_big
        m_last = _re.search(r'(\d+\/\d{4}\s*-\s*[^\s]+)', tail)
        last_val = str(d.get(order[-1], "")).strip() or (m_last.group(1) if m_last else "")
        # Drop trailing "ΣΥΖΗΤΗΘΗΚΕ"
        last_val = _re.sub(r'\s*ΣΥΖΗΤΗΘΗΚΕ\s*$', '', last_val).strip()
        fixed[order[-1]] = last_val

        d = fixed
    else:
        # Even when not shifted, clean the last field
        d[order[-1]] = _re.sub(r'\s*ΣΥΖΗΤΗΘΗΚΕ\s*$', '', str(d.get(order[-1], ""))).strip()

    return d
