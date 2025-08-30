from playwright.sync_api import sync_playwright
import time, re

URL = "https://extapps.solon.gov.gr/mojwp/faces/TrackLdoPublic"

# ADF selectors (escaped :)
SEL_KATASTIMA   = "#courtOfficeOC\\:\\:content"
SEL_GAK_NUMBER  = "#it1\\:\\:content"
SEL_GAK_YEAR    = "#it2\\:\\:content"
SEL_SEARCH_BTN  = "#ldoSearch a"

SEL_GRID        = "#pc1\\:ldoTable"
SEL_GRID_DB     = "#pc1\\:ldoTable\\:\\:db"
SEL_GRID_SPIN   = "#pc1\\:ldoTable\\:\\:sm"

def _norm(s):
    return (s or "").replace("\u00A0", " ").strip()

def _accept_cookies(page):
    for name in ["Αποδοχή","Αποδέχομαι","Συμφωνώ","Accept","Accept all"]:
        try:
            btn = page.get_by_role("button", name=name)
            if btn.count() and btn.first.is_visible():
                btn.first.click()
                page.wait_for_timeout(120)
                return
        except Exception:
            pass

def _select_court_by_label(page, label: str):
    label = (label or "").strip()
    if not label:
        return
    # try by visible label
    try:
        page.select_option(SEL_KATASTIMA, label=label)
        page.wait_for_timeout(60)
        return
    except Exception:
        pass
    # fuzzy fallback: pick first option whose text contains label (case-insensitive, accent-insensitive naive)
    try:
        texts  = page.locator(f"{SEL_KATASTIMA} option").all_text_contents()
        values = page.locator(f"{SEL_KATASTIMA} option").evaluate_all("els => els.map(e=>e.value)")
        lab = re.sub(r"[\s·]+"," ", label, flags=re.U).lower()
        pick = None
        for t, v in zip(texts, values):
            tt = re.sub(r"[\s·]+"," ", t or "", flags=re.U).lower()
            if lab and lab in tt:
                pick = v; break
        if pick:
            page.select_option(SEL_KATASTIMA, value=pick)
            page.wait_for_timeout(60)
    except Exception:
        pass

def _click_search(page):
    try:
        page.locator(SEL_SEARCH_BTN).click(timeout=2000)
        return
    except Exception:
        pass
    try:
        page.evaluate("(sel)=>{const el=document.querySelector(sel); if(el){el.click();}}", SEL_SEARCH_BTN)
    except Exception:
        pass

def _wait_results(page, timeout_ms=30000):
    page.wait_for_selector(SEL_GRID, state="visible", timeout=timeout_ms)
    # spinner visible->hidden if it shows
    try:
        page.wait_for_selector(SEL_GRID_SPIN, state="visible", timeout=2000)
    except Exception:
        pass
    try:
        page.wait_for_selector(SEL_GRID_SPIN, state="hidden", timeout=timeout_ms)
    except Exception:
        pass
    # also wait until either "no data" or some td appears
    page.wait_for_function(
        """
        (dbSel) => {
          const db = document.querySelector(dbSel);
          if (!db) return false;
          const txt = (db.textContent||'').trim();
          const hasNoData = txt.includes('Δεν υπάρχουν δεδομένα');
          const hasTd = !!db.querySelector('td');
          return hasNoData || hasTd;
        }
        """,
        arg=SEL_GRID_DB,
        timeout=timeout_ms
    )

def _extract_row_fields(page, gak_num: str, gak_year: str) -> dict:
    """
    Find the row for ΓΑΚ num/year and map ADF cells by td id suffix:
      :c2  -> Ημ. Κατάθεσης
      :c3  -> Γενικός Αριθμός Κατάθεσης/Έτος
      :c4  -> Ειδικός Αριθμός Κατάθεσης/Έτος
      :c5  -> Διαδικασία
      :c6  -> Είδος
      :c7  -> Αντικείμενο
      :c9  -> Αριθμός Πινακίου
      :c10 -> Αριθμός Απόφασης/Έτος - Είδος Διατακτικού
      :c11 -> Αποτέλεσμα Συζήτησης
    """
    js = r"""
    (args) => {
      const { dbSel, num, year } = args;
      const db = document.querySelector(dbSel);
      if (!db) return null;

      const norm = s => (s||'').toString().replace(/\u00A0/g,' ').replace(/\s+/g,' ').trim();
      const needleNum  = norm(String(num));
      const needleYear = norm(String(year));
      const esc = s => s.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
      const rxCombined = new RegExp('^\\s*'+esc(needleNum)+'\\s*/\\s*'+esc(needleYear)+'\\s*$');

      const map = {
        ':c2':  'Ημ. Κατάθεσης',
        ':c3':  'Γενικός Αριθμός Κατάθεσης/Έτος',
        ':c4':  'Ειδικός Αριθμός Κατάθεσης/Έτος',
        ':c5':  'Διαδικασία',
        ':c6':  'Είδος',
        ':c7':  'Αντικείμενο',
        ':c9':  'Αριθμός Πινακίου',
        ':c10': 'Αριθμός Απόφασης/Έτος - Είδος Διατακτικού',
        ':c11': 'Αποτέλεσμα Συζήτησης',
      };

      const rows = Array.from(db.querySelectorAll('tr'));
      for (const tr of rows) {
        const tds = Array.from(tr.querySelectorAll('td'));
        if (!tds.length) continue;
        const texts = tds.map(td => norm(td.innerText));
        const hasNumExact  = texts.some(t => t === needleNum);
        const hasYearExact = texts.some(t => t === needleYear);
        const hasCombined  = texts.some(t => rxCombined.test(t));
        if (!((hasNumExact && hasYearExact) || hasCombined)) continue;

        const out = {};
        for (const td of tds) {
          const id  = td.id || '';
          const txt = norm(td.innerText);
          for (const suf in map) {
            if (id.endsWith(suf)) {
              out[map[suf]] = txt;
              break;
            }
          }
        }

        // Fallback: if decision cell missing, grab any "1234/2025 - ..." snippet from the row
        if (!out['Αριθμός Απόφασης/Έτος - Είδος Διατακτικού']) {
          const dec = texts.find(t => /\d+\/\d{4}\s*-\s*\S/.test(t));
          if (dec) out['Αριθμός Απόφασης/Έτος - Είδος Διατακτικού'] = dec;
        }

        return out;
      }
      return {};
    }
    """
    return page.evaluate(js, {"dbSel": SEL_GRID_DB, "num": str(gak_num).strip(), "year": str(gak_year).strip()}) or {}

def scrape_solon_civil_adf(court_label: str, gak_number: str, gak_year: int) -> dict:
    """
    Returns:
      {
        "Κατάστημα": <court_label>,
        "ΓΑΚ": "<num>/<year>",
        "fields": { ... all greek keys mapped ... }
      }
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(locale="el-GR", viewport={"width": 1500, "height": 950})
        page = context.new_page()
        page.set_default_timeout(30_000)

        try:
            page.goto(URL, wait_until="domcontentloaded")
            page.wait_for_load_state("networkidle")
            _accept_cookies(page)

            _select_court_by_label(page, court_label)
            page.fill(SEL_GAK_NUMBER, str(gak_number).strip())
            page.fill(SEL_GAK_YEAR,   str(gak_year).strip())

            _click_search(page)
            _wait_results(page, timeout_ms=60_000)

            fields = _extract_row_fields(page, gak_number, gak_year)

            # Massage obvious formats
            if "Ημ. Κατάθεσης" in fields:
                m = re.search(r"\b(\d{2}/\d{2}/\d{4})\b", fields["Ημ. Κατάθεσης"])
                if m:
                    fields["Ημ. Κατάθεσης"] = m.group(1)

            return {
                "Κατάστημα": court_label or "",
                "ΓΑΚ": f"{str(gak_number).strip()}/{str(gak_year).strip()}",
                "fields": fields,
            }
        finally:
            context.close()
            browser.close()
