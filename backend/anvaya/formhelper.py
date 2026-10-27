"""Form Helper for prepared drafts: a copy-ready view, the scheme's application steps, the official link with a QR code,
and a PDF (en / hi / te). Nothing is ever submitted to an external portal: the citizen takes the draft to the office or
portal themselves, and every page says so.

- Fields are listed in the order official forms usually ask for them, each with its source tag (confirmed / inferred /
  citizen-entered / missing). Missing fields say what to bring. Aadhaar and bank account numbers are never collected:
  they are listed as "provide at the office", and any long digit run in a citizen-typed value is masked.
- Steps are the dataset's application_process, split into a numbered checklist; hi / te are VerbX machine translations
  (cached, labelled "machine translation"), never used for eligibility.
- Owner (the draft's session, with the same ownership rules as the session) or a reviewer / admin when the draft has a
  case the citizen consented to share.
"""
import io
import json
import re
from pathlib import Path

from flask import g

from . import i18n, profile, translation
from .cases import DRAFT_SQL, _case_of, normalize_code
from .common import ApiError, audit, current_user, sha256
from .db import get_db, iso

FONT_DIR = Path(__file__).resolve().parent / "data" / "fonts"
LANGS = ("en", "hi", "te")

# The order official application forms usually follow: identity, then address, then household and income.
FORM_ORDER = ["applicant_name", "gender", "date_of_birth", "age", "marital_status", "state", "district", "area",
              "household_size", "annual_income", "occupation", "bpl", "has_bank_account", "receives_other_pension",
              "owns_cultivable_land", "owns_pucca_house"]
TAGS = ("confirmed", "inferred", "citizen_entered", "missing")

TEXT = {
    "watermark": {"en": "Draft prepared by Anvaya AI — not submitted to any government office",
                  "hi": "Anvaya AI द्वारा तैयार ड्राफ़्ट — किसी सरकारी कार्यालय में जमा नहीं किया गया",
                  "te": "Anvaya AI తయారుచేసిన డ్రాఫ్ట్ — ఏ ప్రభుత్వ కార్యాలయంలోనూ సమర్పించలేదు"},
    "title": {"en": "Application draft", "hi": "आवेदन ड्राफ़्ट", "te": "దరఖాస్తు డ్రాఫ్ట్"},
    "fields": {"en": "Details for the form", "hi": "फ़ॉर्म के लिए जानकारी", "te": "ఫారం కోసం వివరాలు"},
    "field": {"en": "Field", "hi": "विवरण", "te": "వివరం"},
    "value": {"en": "Value", "hi": "मान", "te": "విలువ"},
    "source": {"en": "Source", "hi": "स्रोत", "te": "మూలం"},
    "confirmed": {"en": "confirmed", "hi": "पुष्टि की गई", "te": "నిర్ధారించబడింది"},
    "inferred": {"en": "inferred — check", "hi": "अनुमानित — जाँचें", "te": "ఊహించినది — తనిఖీ చేయండి"},
    "citizen_entered": {"en": "citizen-entered", "hi": "नागरिक द्वारा भरा", "te": "పౌరులు నమోదు చేసినది"},
    "missing": {"en": "missing", "hi": "नहीं है", "te": "లేదు"},
    "bring": {"en": "Bring to the office", "hi": "कार्यालय में साथ लाएँ", "te": "కార్యాలయానికి తీసుకురండి"},
    "documents": {"en": "Document checklist", "hi": "दस्तावेज़ सूची", "te": "పత్రాల జాబితా"},
    "case": {"en": "Case with an Anvaya reviewer", "hi": "Anvaya समीक्षक के पास केस", "te": "Anvaya సమీక్షకుని వద్ద కేసు"},
    "case_code": {"en": "Case code", "hi": "केस कोड", "te": "కేసు కోడ్"},
    "steps": {"en": "How to apply", "hi": "आवेदन कैसे करें", "te": "ఎలా దరఖాస్తు చేయాలి"},
    "mt": {"en": "machine translation", "hi": "मशीन अनुवाद", "te": "యంత్ర అనువాదం"},
    "steps_english": {"en": "", "hi": "चरण अंग्रेज़ी में (अनुवाद उपलब्ध नहीं)", "te": "దశలు ఆంగ్లంలో (అనువాదం అందుబాటులో లేదు)"},
    "no_steps": {"en": "The catalogue has no application steps for this scheme; ask at the office.",
                 "hi": "इस योजना के लिए आवेदन के चरण उपलब्ध नहीं हैं; कार्यालय में पूछें।",
                 "te": "ఈ పథకానికి దరఖాస్తు దశలు అందుబాటులో లేవు; కార్యాలయంలో అడగండి."},
    "official_link": {"en": "Official source / portal", "hi": "आधिकारिक स्रोत / पोर्टल", "te": "అధికారిక మూలం / పోర్టల్"},
    "prepared": {"en": "Prepared", "hi": "तैयार", "te": "తయారు"},
    "footer": {"en": "Anvaya AI does not submit applications. Check every detail before you submit it yourself.",
               "hi": "Anvaya AI आवेदन जमा नहीं करता। ख़ुद जमा करने से पहले हर जानकारी जाँच लें।",
               "te": "Anvaya AI దరఖాస్తులను సమర్పించదు. మీరే సమర్పించే ముందు ప్రతి వివరాన్ని తనిఖీ చేయండి."},
    "draft_badge": {"en": "DRAFT · NOT SUBMITTED", "hi": "ड्राफ़्ट · जमा नहीं किया गया", "te": "డ్రాఫ్ట్ · సమర్పించలేదు"},
    "scan": {"en": "Scan to open the official page", "hi": "आधिकारिक पेज खोलने के लिए स्कैन करें",
             "te": "అధికారిక పేజీ తెరవడానికి స్కాన్ చేయండి"},
    "page": {"en": "Page", "hi": "पृष्ठ", "te": "పేజీ"},
    "draft_id": {"en": "Draft ID", "hi": "ड्राफ़्ट आईडी", "te": "డ్రాఫ్ట్ ఐడీ"},
    "version": {"en": "Version", "hi": "संस्करण", "te": "వెర్షన్"},
    "masked": {"en": "(number hidden — give it at the office)", "hi": "(नंबर छिपाया गया — कार्यालय में दें)",
               "te": "(నంబర్ దాచబడింది — కార్యాలయంలో ఇవ్వండి)"},
}

# What to bring when a field is missing.
BRING = {
    "applicant_name": {"en": "Your name exactly as on your ID card", "hi": "पहचान पत्र पर लिखा आपका पूरा नाम",
                       "te": "గుర్తింపు కార్డులో ఉన్నట్లుగా మీ పూర్తి పేరు"},
    "date_of_birth": {"en": "Proof of age (birth or school certificate, or ID card)",
                      "hi": "उम्र का प्रमाण (जन्म या स्कूल प्रमाणपत्र, या पहचान पत्र)",
                      "te": "వయస్సు రుజువు (జనన లేదా పాఠశాల ధృవీకరణ పత్రం, లేదా గుర్తింపు కార్డు)"},
    "state": {"en": "Address proof (ration card or voter ID)", "hi": "पते का प्रमाण (राशन कार्ड या वोटर आईडी)",
              "te": "చిరునామా రుజువు (రేషన్ కార్డు లేదా ఓటరు గుర్తింపు కార్డు)"},
    "annual_income": {"en": "Income certificate from the revenue office", "hi": "राजस्व कार्यालय से आय प्रमाणपत्र",
                      "te": "రెవెన్యూ కార్యాలయం నుండి ఆదాయ ధృవీకరణ పత్రం"},
    "household_size": {"en": "Ration card showing the family members", "hi": "परिवार के सदस्यों वाला राशन कार्ड",
                       "te": "కుటుంబ సభ్యులను చూపే రేషన్ కార్డు"},
    "_default": {"en": "Tell the officer; bring proof if asked", "hi": "अधिकारी को बताएँ; माँगे जाने पर प्रमाण लाएँ",
                 "te": "అధికారికి చెప్పండి; అడిగితే రుజువు తీసుకురండి"},
}
BRING["age"] = BRING["date_of_birth"]
BRING["district"] = BRING["state"]

# Never collected by Anvaya: always listed for the office.
OFFICE_ONLY = [
    {"key": "aadhaar_number",
     "label": {"en": "Aadhaar number", "hi": "आधार नंबर", "te": "ఆధార్ నంబర్"},
     "hint": {"en": "Provide at the office — Anvaya never asks for it", "hi": "कार्यालय में दें — Anvaya इसे कभी नहीं माँगता",
              "te": "కార్యాలయంలో ఇవ్వండి — Anvaya దీన్ని ఎప్పుడూ అడగదు"}},
    {"key": "bank_account",
     "label": {"en": "Bank account number and IFSC", "hi": "बैंक खाता नंबर और IFSC", "te": "బ్యాంక్ ఖాతా నంబర్ మరియు IFSC"},
     "hint": {"en": "Bring your passbook to the office — Anvaya never asks for it",
              "hi": "पासबुक कार्यालय में लाएँ — Anvaya इसे कभी नहीं माँगता",
              "te": "పాస్‌బుక్‌ను కార్యాలయానికి తీసుకురండి — Anvaya దీన్ని ఎప్పుడూ అడగదు"}},
]

# A run of 9+ digits (spaces / hyphens allowed between them) looks like an Aadhaar, bank account or phone number.
LONG_DIGITS = re.compile(r"\d(?:[\s-]?\d){8,}")
AADHAAR_SHAPED = re.compile(r"(?<!\d)\d{4}[\s-]?\d{4}[\s-]?\d{4}(?!\d)")
URL_RE = re.compile(r"https?://[^\s\]\)\"'<>]+")


def t(key: str, lang: str) -> str:
    return i18n.t(TEXT, key, lang)


def mask_citizen_value(text: str, lang: str) -> str:
    """Citizen-typed text never carries an ID or account number into the draft view or PDF."""
    return LONG_DIGITS.sub(t("masked", lang), text)


def mask_dataset_text(text: str) -> str:
    """Dataset text keeps helpline numbers but never anything shaped like an Aadhaar number."""
    return AADHAAR_SHAPED.sub("XXXX XXXX XXXX", text)


# ---------------------------------------------------------------- access

def load(draft_id: str, session_id: str | None) -> tuple[dict, dict | None]:
    """The draft row (as a dict) and the staff user, if a reviewer / admin is reading. Owner = the draft's session
    (X-Session-Id) with the session's ownership rules (account token, kiosk device + operator)."""
    db = get_db()
    row = db.execute(DRAFT_SQL + " WHERE d.draft_id=?", (draft_id,)).fetchone()
    if not row:
        raise ApiError("DRAFT_NOT_FOUND", "Draft not found.", 404)
    row = dict(row)
    staff = current_user()  # a staff token below aal2 is refused here (MFA_REQUIRED)
    if staff and staff["role"] in ("reviewer", "admin"):
        g.user = staff
        if not row["case_case_id"]:
            raise ApiError("FORBIDDEN", "Reviewers see a draft only after the citizen shares it.", 403)
        return row, staff
    if not session_id or row["session_id"] != session_id:
        raise ApiError("FORBIDDEN", "This draft belongs to another session.", 403)
    profile.check_owner(row)
    return row, None


def _case_code(row: dict, offered: str | None) -> str | None:
    """Case codes are stored hashed: the code is shown only when the citizen's browser offers it and it matches."""
    if not offered or not row["case_case_id"]:
        return None
    code = normalize_code(offered)
    stored = get_db().execute("SELECT code_hash FROM cases WHERE case_id=?", (row["case_case_id"],)).fetchone()
    return code if stored and stored[0] and sha256(code) == stored[0] else None


# ---------------------------------------------------------------- content

def tag_of(provenance: str) -> str:
    return {"confirmed": "confirmed", "citizen_entered": "citizen_entered", "missing": "missing"}.get(provenance, "inferred")


def ordered_fields(fields: list[dict], lang: str) -> list[dict]:
    rank = {k: i for i, k in enumerate(FORM_ORDER)}
    out = []
    for f in sorted(fields, key=lambda f: (rank.get(f["key"], len(FORM_ORDER)), f["key"])):
        tag = tag_of(f["provenance"])
        value = None
        if f["value"] is not None and tag != "missing":
            value = mask_citizen_value(profile.display_value(f["key"], f["value"], lang), lang)
        out.append({"key": f["key"], "label": i18n.t(i18n.ATTRIBUTE_LABELS, f["key"], lang), "value": value,
                    "copy_text": value, "tag": tag, "tag_label": t(tag, lang), "fact_id": f.get("fact_id"),
                    "bring": i18n.t(BRING, f["key"] if f["key"] in BRING else "_default", lang) if tag == "missing" else None})
    return out


def parse_steps(text: str | None) -> list[dict]:
    """application_process → numbered steps. "Process 1:"-style lines become headings; "Step 1:", "1.", bullets are
    stripped; mojibake from the source CSV and empty markdown links are cleaned up."""
    if not text:
        return []
    text = text.replace("�", "").replace(" ", " ")
    text = re.sub(r"\[(https?://[^\]]+)\]\(\)", r"\1", text)
    steps = []
    for raw in text.splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
        if not line:
            continue
        heading = bool(re.fullmatch(r"(process|method|mode|option|offline|online)[\w\s()/-]{0,30}:?", line, re.I)) \
            or (line.endswith(":") and len(line) <= 40)
        line = re.sub(r"^(step\s*\d+\s*[:.)-]?|\d+\s*[.)]|[-•*–])\s*", "", line, flags=re.I).strip()
        if line:
            steps.append({"text": mask_dataset_text(line[:500]), "heading": heading})
        if len(steps) >= 30:
            break
    return steps


def official_links(scheme: dict) -> tuple[dict | None, list[dict]]:
    """(the portal / official link, all source links) from the dataset; http(s) only."""
    try:
        links = [u for u in json.loads(scheme.get("source_urls_json") or "[]") if isinstance(u, dict)]
    except ValueError:
        links = []
    links = [{"label": (u.get("label") or "Source")[:80], "url": u["url"]} for u in links
             if isinstance(u.get("url"), str) and URL_RE.fullmatch(u["url"])]
    if not links and scheme.get("source_url"):
        m = URL_RE.search(scheme["source_url"])
        if m:
            links = [{"label": "Source", "url": m.group(0)}]
    portal = next((u for u in links if re.search(r"official|portal|website|apply|online", u["label"], re.I)), None)
    return portal or (links[0] if links else None), links


def scheme_row(scheme_id: str) -> dict:
    row = get_db().execute("SELECT * FROM schemes WHERE scheme_id=?", (scheme_id,)).fetchone()
    return dict(row) if row else {}


def helper(row: dict, lang: str, case_code: str | None = None) -> dict:
    """Everything the draft page and the PDF show, in `lang`."""
    if lang not in LANGS:
        raise ApiError("UNSUPPORTED_LANGUAGE", "Supported languages: en, hi, te.", 422)
    body = json.loads(row["fields_json"])
    scheme = scheme_row(row["scheme_id"])
    steps = parse_steps(scheme.get("application_process"))
    translated = translation.translate_many([s["text"] for s in steps], "en", lang) if lang != "en" and steps else {}
    for s in steps:
        local = translated.get(s["text"])
        s.update(text_en=s["text"], text=mask_dataset_text(local) if local else s["text"], machine_translated=bool(local))
    portal, links = official_links(scheme)
    case = _case_of(row)
    status = i18n.t(i18n.CASE_STATUS, "DRAFT_SAVED", lang)
    return {
        "draft_id": row["draft_id"], "version": row["version"], "scheme_id": row["scheme_id"],
        "scheme_name": body.get("scheme_name") or scheme.get("name"), "language": lang,
        "status_label": status,
        "case": {**case, "status_label": i18n.t(i18n.CASE_STATUS, case["status"], lang), "code": case_code}
        if case else None,
        "fields": ordered_fields(body.get("fields", []), lang),
        "office_only": [{"key": o["key"], "label": o["label"][lang], "hint": o["hint"][lang]} for o in OFFICE_ONLY],
        "documents": [{"doc_key": d["doc_key"], "label": i18n.doc_label(d["doc_key"], lang)[0], "status": d["status"],
                       "status_label": i18n.t(i18n.DOC_STATUS, d["status"], lang),
                       "ready": d["status"] in ("available", "uploaded", "verified")}
                      for d in body.get("documents", [])],
        "steps": steps,
        "steps_machine_translated": any(s["machine_translated"] for s in steps),
        "steps_note": t("steps_english", lang) if lang != "en" and steps and not translated else None,
        "official_link": portal, "links": links,
        "qr_url": f"/api/v1/schemes/{row['scheme_id']}/portal-qr.svg" if portal else None,
        "watermark": t("watermark", "en"), "watermark_local": t("watermark", lang),
        "labels": {k: t(k, lang) for k in ("bring", "documents", "steps", "mt", "official_link", "fields", "case_code",
                                           "footer")},
    }


def portal_qr_svg(scheme_id: str) -> str:
    import segno
    portal, _ = official_links(scheme_row(scheme_id))
    if not portal:
        raise ApiError("NO_OFFICIAL_LINK", "The catalogue has no official link for this scheme.", 404)
    buf = io.BytesIO()
    segno.make(portal["url"], error="m").save(buf, kind="svg", scale=4, border=2, xmldecl=False)
    return buf.getvalue().decode()


# ---------------------------------------------------------------- PDF

# Palette (RGB): the site's deep green, a warm amber for "needs attention", neutral greys.
INK, MUTED, RULE = (29, 36, 34), (95, 105, 102), (222, 226, 224)
BRAND, BRAND_SOFT = (15, 92, 77), (232, 243, 240)
AMBER, AMBER_SOFT = (176, 108, 0), (253, 242, 220)
GREEN, BLUE = (31, 122, 58), (21, 94, 156)
TAG_COLOR = {"confirmed": GREEN, "citizen_entered": GREEN, "inferred": BLUE, "missing": AMBER}


def render_pdf(h: dict) -> bytes:
    """The draft as a PDF in h["language"] with Noto fonts (HarfBuzz shaping for Devanagari / Telugu): a branded header
    band, a title block with the draft details, a ruled table with the source of every value, a "bring to the office"
    panel, the document checklist, numbered steps and the official link with its QR code."""
    import segno
    from fpdf import FPDF

    lang = h["language"]
    script = {"hi": "deva", "te": "telu"}.get(lang)

    class DraftPDF(FPDF):
        def header(self):
            # Faint watermark on every page, under the content.
            self.set_font("noto", "B", 19)
            self.set_text_color(238, 238, 238)
            with self.rotation(32, x=self.w / 2, y=self.h / 2):
                text = h["watermark"]
                self.text(self.w / 2 - self.get_string_width(text) / 2, self.h / 2, text)
            # Brand band.
            self.set_fill_color(*BRAND)
            self.rect(0, 0, self.w, 15, style="F")
            self.set_fill_color(232, 131, 58)
            self.rect(0, 15, self.w, 1, style="F")
            self.set_text_color(255, 255, 255)
            self.set_font("noto", "B", 13)
            self.set_xy(self.l_margin, 4.2)
            self.cell(40, 7, "Anvaya AI")
            self.set_font("noto", "", 8.5)
            badge = t("draft_badge", lang)
            self.set_xy(self.w - self.r_margin - 80, 5)
            self.cell(80, 5, badge, align="R")
            self.set_text_color(*INK)
            self.set_y(22)

        def footer(self):
            self.set_y(-17)
            self.set_draw_color(*RULE)
            self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
            self.ln(1.5)
            self.set_font("noto", "", 7.5)
            self.set_text_color(*MUTED)
            for line in _wrap(self, f"{t('footer', lang)} · {h['watermark_local']}", self.epw - 22):
                self.set_x(self.l_margin)
                self.cell(self.epw - 22, 3.6, line, new_x="LMARGIN", new_y="NEXT")
            self.set_xy(self.w - self.r_margin - 20, -15.5)
            self.cell(20, 4, f"{t('page', lang)} {self.page_no()}", align="R")
            self.set_text_color(*INK)
            self.set_draw_color(0, 0, 0)
            # The footer is the last thing drawn on a page (and the last page's is drawn inside output()), so all
            # glyphs used so far are in the subset now.
            _map_substituted_glyphs(self)

    pdf = DraftPDF(format="A4")
    pdf.set_margins(16, 22, 16)
    pdf.set_auto_page_break(True, margin=22)
    pdf.set_title(f"{h['scheme_name']} — draft")
    pdf.set_author("Anvaya AI")
    pdf.set_creator("Anvaya AI")
    pdf.set_subject(t("title", lang))
    pdf.add_font("noto", "", str(FONT_DIR / "NotoSans-Regular.ttf"))
    pdf.add_font("noto", "B", str(FONT_DIR / "NotoSans-Bold.ttf"))
    if script == "deva":
        pdf.add_font("script", "", str(FONT_DIR / "NotoSansDevanagari-Regular.ttf"))
        pdf.add_font("script", "B", str(FONT_DIR / "NotoSansDevanagari-Bold.ttf"))
    elif script == "telu":
        pdf.add_font("script", "", str(FONT_DIR / "NotoSansTelugu-Regular.ttf"))
        pdf.add_font("script", "B", str(FONT_DIR / "NotoSansTelugu-Bold.ttf"))
    if script:
        # One script font per document: fpdf2's fallback switching is reliable with a single fallback.
        pdf.set_fallback_fonts(["script"], exact_match=False)
    pdf.set_text_shaping(True)
    pdf.add_page()

    def room(height):
        if pdf.get_y() + height > pdf.h - 24:
            pdf.add_page()

    def para(text, size=10, style="", gap=1.5, indent=0.0, color=INK, width=None):
        pdf.set_font("noto", style, size)
        pdf.set_text_color(*color)
        lh = size * 0.5
        w = (width if width is not None else pdf.epw) - indent
        for line in _wrap(pdf, text, w):
            room(lh)
            pdf.set_x(pdf.l_margin + indent)
            pdf.cell(w, lh, line, new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(*INK)
        pdf.ln(gap)

    def heading(text):
        room(16)
        pdf.ln(4)
        y = pdf.get_y()
        pdf.set_fill_color(*BRAND)
        pdf.rect(pdf.l_margin, y + 0.6, 1.4, 6, style="F")
        pdf.set_xy(pdf.l_margin + 4, y)
        pdf.set_font("noto", "B", 12.5)
        pdf.set_text_color(*BRAND)
        pdf.cell(pdf.epw - 4, 7.2, text, new_x="LMARGIN", new_y="NEXT")
        pdf.set_draw_color(*RULE)
        pdf.line(pdf.l_margin, pdf.get_y() + 0.8, pdf.w - pdf.r_margin, pdf.get_y() + 0.8)
        pdf.set_draw_color(0, 0, 0)
        pdf.set_text_color(*INK)
        pdf.ln(3.5)

    # ---- title block
    para(t("title", lang).upper() if lang == "en" else t("title", lang), 9, "B", gap=0.5, color=MUTED)
    para(h["scheme_name"], 19, "B", gap=2.5, color=BRAND)
    pill = h["status_label"]
    pdf.set_font("noto", "B", 9.5)
    pw = min(pdf.epw, pdf.get_string_width(pill) + 10)
    y = pdf.get_y()
    pdf.set_fill_color(*AMBER_SOFT)
    pdf.set_draw_color(*AMBER)
    pdf.rect(pdf.l_margin, y, pw, 7.4, style="DF", round_corners=True, corner_radius=3.7)
    pdf.set_text_color(*AMBER)
    pdf.set_xy(pdf.l_margin + 5, y + 0.9)
    pdf.cell(pw - 10, 5.6, pill)
    pdf.set_text_color(*INK)
    pdf.set_draw_color(0, 0, 0)
    pdf.set_y(y + 11)

    # Details strip: draft id, version, prepared date (and the case code when the citizen shared the draft).
    cells = [(t("draft_id", lang), h["draft_id"]), (t("version", lang), f"v{h['version']}"), (t("prepared", lang), iso()[:10])]
    if h["case"] and h["case"].get("code"):
        cells.append((t("case_code", lang), h["case"]["code"]))
    y = pdf.get_y()
    pdf.set_fill_color(*BRAND_SOFT)
    pdf.rect(pdf.l_margin, y, pdf.epw, 13, style="F")
    colw = pdf.epw / len(cells)
    for i, (k, v) in enumerate(cells):
        pdf.set_xy(pdf.l_margin + i * colw + 4, y + 1.6)
        pdf.set_font("noto", "", 7.5)
        pdf.set_text_color(*MUTED)
        pdf.cell(colw - 4, 4, k)
        pdf.set_xy(pdf.l_margin + i * colw + 4, y + 6)
        pdf.set_font("noto", "B", 10 if len(v) < 22 else 8.5)
        pdf.set_text_color(*INK)
        pdf.cell(colw - 4, 5, v)
    pdf.set_y(y + 14)
    if h["case"]:
        pdf.ln(1.5)
        para(f"{t('case', lang)}: {h['case']['case_id']} — {h['case']['status_label']}", 9, color=MUTED)

    # ---- details table
    heading(t("fields", lang))
    widths = [pdf.epw * 0.34, pdf.epw * 0.40, pdf.epw * 0.26]
    _row(pdf, [t("field", lang), t("value", lang), t("source", lang)], widths, head=True)
    for i, f in enumerate(h["fields"]):
        value = f["value"] if f["value"] is not None else f"— {t('bring', lang)}: {f['bring']}"
        _row(pdf, [f["label"], value, f["tag_label"]], widths, shade=f["tag"] == "missing", zebra=i % 2 == 1,
             tag_color=TAG_COLOR.get(f["tag"]))
    pdf.set_draw_color(*RULE)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + sum(widths), pdf.get_y())
    pdf.set_draw_color(0, 0, 0)

    # ---- bring to the office: a panel
    heading(t("bring", lang))
    items = [f"{o['label']}: {o['hint']}" for o in h["office_only"]]
    items += [f"{f['label']}: {f['bring']}" for f in h["fields"] if f["tag"] == "missing"]
    pdf.set_font("noto", "", 9.5)
    lines = [_wrap(pdf, it, pdf.epw - 14) for it in items]
    box_h = sum(len(ls) * 5 + 1.6 for ls in lines) + 5
    room(box_h)
    y = pdf.get_y()
    pdf.set_fill_color(*AMBER_SOFT)
    pdf.rect(pdf.l_margin, y, pdf.epw, box_h, style="F")
    pdf.set_fill_color(*AMBER)
    pdf.rect(pdf.l_margin, y, 1.4, box_h, style="F")
    cy = y + 3
    for ls in lines:
        pdf.set_fill_color(*AMBER)
        pdf.ellipse(pdf.l_margin + 6, cy + 1.7, 1.4, 1.4, style="F")
        for j, line in enumerate(ls):
            pdf.set_xy(pdf.l_margin + 10, cy)
            pdf.cell(pdf.epw - 14, 5, line)
            cy += 5
        cy += 1.6
    pdf.set_y(y + box_h)

    # ---- document checklist
    heading(t("documents", lang))
    for d in h["documents"]:
        pdf.set_font("noto", "", 10)
        room(7)
        y = pdf.get_y()
        if d["ready"]:
            pdf.set_fill_color(*GREEN)
            pdf.rect(pdf.l_margin, y + 0.9, 4.2, 4.2, style="F", round_corners=True, corner_radius=0.8)
            pdf.set_draw_color(255, 255, 255)
            pdf.set_line_width(0.5)
            pdf.line(pdf.l_margin + 0.9, y + 3.1, pdf.l_margin + 1.8, y + 4.1)
            pdf.line(pdf.l_margin + 1.8, y + 4.1, pdf.l_margin + 3.4, y + 1.8)
            pdf.set_line_width(0.2)
            pdf.set_draw_color(0, 0, 0)
        else:
            pdf.set_draw_color(*MUTED)
            pdf.rect(pdf.l_margin, y + 0.9, 4.2, 4.2, round_corners=True, corner_radius=0.8)
            pdf.set_draw_color(0, 0, 0)
        para(f"{d['label']} — {d['status_label']}", 10, gap=1.2, indent=8, color=INK if d["ready"] else (60, 66, 64))

    # ---- steps
    heading(t("steps", lang) + (f" ({t('mt', lang)})" if h["steps_machine_translated"] else ""))
    if h["steps_note"]:
        para(h["steps_note"], 9, color=MUTED)
    if not h["steps"]:
        para(t("no_steps", lang), 10)
    n = 0
    for s in h["steps"]:
        if s["heading"]:
            para(s["text"], 10, "B", gap=1, color=BRAND)
            n = 0
            continue
        n += 1
        pdf.set_font("noto", "", 9.5)
        need = len(_wrap(pdf, s["text"], pdf.epw - 11)) * 4.75 + 3
        room(need)
        y = pdf.get_y()
        pdf.set_fill_color(*BRAND_SOFT)
        pdf.ellipse(pdf.l_margin, y + 0.2, 5.6, 5.6, style="F")
        pdf.set_font("noto", "B", 8.5)
        pdf.set_text_color(*BRAND)
        pdf.set_xy(pdf.l_margin, y + 0.9)
        pdf.cell(5.6, 4.2, str(n), align="C")
        pdf.set_text_color(*INK)
        pdf.set_y(y)
        para(s["text"], 9.5, gap=2, indent=9)

    # ---- official link + QR
    if h["official_link"]:
        heading(t("official_link", lang))
        buf = io.BytesIO()
        segno.make(h["official_link"]["url"], error="m").save(buf, kind="png", scale=6, border=1)
        room(36)
        y = pdf.get_y()
        pdf.set_draw_color(*RULE)
        pdf.set_fill_color(250, 251, 250)
        pdf.rect(pdf.l_margin, y, pdf.epw, 33, style="DF", round_corners=True, corner_radius=2)
        pdf.set_draw_color(0, 0, 0)
        pdf.image(io.BytesIO(buf.getvalue()), x=pdf.l_margin + 3, y=y + 3, w=27)
        tx = pdf.l_margin + 34
        pdf.set_xy(tx, y + 4)
        pdf.set_y(y + 4)
        para(t("scan", lang), 9, "B", gap=1.5, indent=34, color=BRAND)
        para(f"{h['official_link']['label']}: {h['official_link']['url']}", 8.5, gap=0, indent=34, color=MUTED)
        pdf.set_y(y + 35)

    return bytes(pdf.output())  # the last footer (rendered here) maps the glyphs it adds


def _wrap(pdf, text: str, width: float) -> list[str]:
    """Word wrap measured with the current font (fpdf2's own wrapping fails on shaped fallback runs)."""
    lines = []
    for para in str(text).split("\n"):
        line = ""
        for word in para.split(" "):
            cand = f"{line} {word}".strip()
            if line and pdf.get_string_width(cand) > width:
                lines.append(line)
                line = word
            else:
                line = cand
            while pdf.get_string_width(line) > width and len(line) > 1:  # a single very long word (a URL)
                cut = len(line)
                while cut > 1 and pdf.get_string_width(line[:cut]) > width:
                    cut -= 1
                lines.append(line[:cut])
                line = line[cut:]
        lines.append(line)
    return lines or [""]


def _row(pdf, cells: list[str], widths: list[float], head=False, shade=False, zebra=False, tag_color=None) -> None:
    pdf.set_font("noto", "B" if head else "", 9.5)
    lh = 5
    wrapped = [_wrap(pdf, c, w - 5) for c, w in zip(cells, widths)]
    height = max(len(w) for w in wrapped) * lh + 3.5
    if pdf.get_y() + height > pdf.h - 24:
        pdf.add_page()
    x0, y0 = pdf.l_margin, pdf.get_y()
    total = sum(widths)
    if head:
        pdf.set_fill_color(*BRAND)
        pdf.rect(x0, y0, total, height, style="F")
    elif shade:
        pdf.set_fill_color(*AMBER_SOFT)
        pdf.rect(x0, y0, total, height, style="F")
    elif zebra:
        pdf.set_fill_color(246, 248, 247)
        pdf.rect(x0, y0, total, height, style="F")
    x = x0
    for col, (lines, w) in enumerate(zip(wrapped, widths)):
        pdf.set_font("noto", "B" if head or col == 0 else "", 9.5)
        if head:
            pdf.set_text_color(255, 255, 255)
        elif col == 2 and tag_color:
            pdf.set_text_color(*tag_color)
            pdf.set_font("noto", "B", 9)
        elif col == 1 and shade:
            pdf.set_text_color(*AMBER)
        else:
            pdf.set_text_color(*INK)
        for i, line in enumerate(lines):
            pdf.set_xy(x + 2.5, y0 + 1.75 + i * lh)
            pdf.cell(w - 5, lh, line)
        x += w
    pdf.set_text_color(*INK)
    if not head:
        pdf.set_draw_color(*RULE)
        pdf.line(x0, y0 + height, x0 + total, y0 + height)
        pdf.set_draw_color(0, 0, 0)
    pdf.set_xy(x0, y0 + height)


def _map_substituted_glyphs(pdf) -> None:
    """HarfBuzz substitutes some glyphs (alternate vowel-sign forms, conjunct parts) that have no Unicode value of
    their own; fpdf2 leaves them out of ToUnicode and text extraction then shows control codes inside words. Map them
    to a zero-width space so copied / extracted text keeps only the real letters."""
    for font in pdf.fonts.values():
        subset = getattr(font, "subset", None)
        if subset is None:
            continue
        for glyph, _ in subset.items():
            if glyph is not None and (not isinstance(glyph.unicode, tuple) or len(glyph.unicode) == 0):
                glyph.unicode = (0x200B,)


def record_download(row: dict, lang: str, staff: dict | None) -> None:
    audit("draft.pdf_downloaded", session_id=row["session_id"], case_id=row["case_case_id"],
          details={"draft_id": row["draft_id"], "language": lang, "by": staff["role"] if staff else "owner"})
    get_db().commit()
