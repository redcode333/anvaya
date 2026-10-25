"""Form Helper: the draft PDF (Hindi / Telugu text layer, watermark, access control, no Aadhaar or bank numbers), the
copy-ready view, application steps (machine translation label), the portal link and QR code, and the status wording."""
import io
import re
import uuid

import pypdf
import pytest
from conftest import bearer, kiosk, staff, token

from anvaya import formhelper, translation

TC1 = ("I am 67 years old, a farmer in a village in Guntur, Andhra Pradesh. Family of 4, yearly income 60,000 rupees. "
       "We have a BPL card, I do not get any pension, I own 2 acres of land and have a bank account.")
WATERMARK = "Draft prepared by Anvaya AI — not submitted to any government office"
HI_WATERMARK = "Anvaya AI द्वारा तैयार ड्राफ़्ट — किसी सरकारी कार्यालय में जमा नहीं किया गया"
TE_WATERMARK = "Anvaya AI తయారుచేసిన డ్రాఫ్ట్ — ఏ ప్రభుత్వ కార్యాలయంలోనూ సమర్పించలేదు"


def squash(text: str) -> str:
    """Compare PDF text without spaces, zero-width and control characters (conjuncts extract with stray spaces)."""
    return re.sub(r"[\s​\x00-\x1f]", "", text)


def pdf_text(data: bytes) -> str:
    return "\n".join(p.extract_text() for p in pypdf.PdfReader(io.BytesIO(data)).pages)


@pytest.fixture()
def fake_translation(monkeypatch):
    """VerbX stand-in: marks every step as translated (hi / te) so the label logic is exercised."""
    def fake(texts, source, target):
        prefix = {"hi": "आवेदन चरण: ", "te": "దరఖాస్తు దశ: "}[target]
        return {t: prefix + t for t in texts}
    monkeypatch.setattr(translation, "translate_many", fake)


def make_draft(client, headers, name="Lakshmi Devi", extra=None, mode="personal"):
    """A citizen session screened for TC1 with a draft; returns (session id, draft)."""
    sid = client.post("/api/v1/sessions", json={"mode": mode, "language": "en"}, headers=headers).json["session_id"]
    client.post(f"/api/v1/sessions/{sid}/turns", json={"utterance": TC1}, headers=headers)
    for fid in client.post(f"/api/v1/sessions/{sid}/profile/confirm-all", headers=headers).json["needs_confirmation"]:
        client.patch(f"/api/v1/sessions/{sid}/profile/facts/{fid}", json={"confirmed": True}, headers=headers)
    ev = client.post(f"/api/v1/sessions/{sid}/eligibility/evaluate", headers=headers).json
    scheme = next(r["scheme_id"] for r in ev["results"] if r["outcome"] != "MISMATCH" and r["jurisdiction"]["level"] == "State")
    d = client.post(f"/api/v1/sessions/{sid}/drafts", json={"scheme_id": scheme},
                    headers={**headers, "Idempotency-Key": uuid.uuid4().hex}).json
    if name:
        d = client.patch(f"/api/v1/drafts/{d['draft_id']}", json={"version": d["version"], "fields": {"applicant_name": name, **(extra or {})}},
                         headers={**headers, "X-Session-Id": sid}).json
    return sid, d


def owner(sid, headers=None):
    return {**(headers or {}), "X-Session-Id": sid}


# ---------------------------------------------------------------- PDF

@pytest.mark.parametrize("lang, label, watermark, status", [
    ("en", "Applicant name", WATERMARK, "Draft ready — submit at the office/portal"),
    ("hi", "आवेदक का नाम", HI_WATERMARK, "ड्राफ़्ट तैयार — कार्यालय/पोर्टल पर जमा करें"),
    ("te", "దరఖాస్తుదారుని పేరు", TE_WATERMARK, "డ్రాఫ్ట్ సిద్ధం — కార్యాలయంలో/పోర్టల్‌లో సమర్పించండి"),
])
def test_pdf_has_the_text_layer_watermark_and_status(client, fake_translation, lang, label, watermark, status):
    h = {}
    sid, d = make_draft(client, h)
    r = client.get(f"/api/v1/drafts/{d['draft_id']}/pdf?language={lang}", headers=owner(sid))
    assert r.status_code == 200 and r.mimetype == "application/pdf" and r.data[:5] == b"%PDF-"
    assert "no-store" in r.headers["Cache-Control"] and "attachment" in r.headers["Content-Disposition"]
    text = squash(pdf_text(r.data))
    assert squash(label) in text
    assert squash("Lakshmi Devi") in text
    assert squash(watermark) in text and squash(WATERMARK) in text  # English watermark on every page too
    assert squash(status) in text
    assert squash("Aadhaar") in text or squash("आधार") in text or squash("ఆధార్") in text


def test_pdf_shows_every_field_with_its_source_tag_and_the_documents(client):
    sid, d = make_draft(client, {})
    body = client.get(f"/api/v1/drafts/{d['draft_id']}/helper", headers=owner(sid)).json
    tags = {f["key"]: f["tag"] for f in body["fields"]}
    assert tags["applicant_name"] == "citizen_entered" and tags["state"] == "confirmed" and set(tags.values()) <= set(formhelper.TAGS)
    text = squash(pdf_text(client.get(f"/api/v1/drafts/{d['draft_id']}/pdf", headers=owner(sid)).data))
    for f in body["fields"]:
        assert squash(f["label"]) in text
        assert squash(f["tag_label"]) in text
    for doc in body["documents"]:
        assert squash(doc["label"]) in text
    assert body["status_label"] == "Draft ready — submit at the office/portal"
    assert "submitted" not in body["status_label"].lower() and "applied" not in body["status_label"].lower()


def test_hindi_and_telugu_fact_values_render(client):
    sid, d = make_draft(client, {}, name="लक्ष्मी देवी")
    text = squash(pdf_text(client.get(f"/api/v1/drafts/{d['draft_id']}/pdf?language=hi", headers=owner(sid)).data))
    assert squash("लक्ष्मी देवी") in text and squash("वर्ष") in text  # name and "years" in Hindi
    sid, d = make_draft(client, {}, name="లక్ష్మి దేవి")
    text = squash(pdf_text(client.get(f"/api/v1/drafts/{d['draft_id']}/pdf?language=te", headers=owner(sid)).data))
    assert squash("లక్ష్మి దేవి") in text and squash("సంవత్సరాలు") in text


def test_pdf_embeds_the_noto_fonts(client):
    sid, d = make_draft(client, {})
    data = client.get(f"/api/v1/drafts/{d['draft_id']}/pdf?language=te", headers=owner(sid)).data
    fonts = {str(f.get("/BaseFont", "")) for p in pypdf.PdfReader(io.BytesIO(data)).pages
             for f in (p["/Resources"].get("/Font") or {}).values() for f in [f.get_object()]}
    joined = " ".join(fonts)
    assert "NotoSans" in joined and "Telugu" in joined


# ---------------------------------------------------------------- access control

def test_only_the_owner_or_a_reviewer_with_a_shared_case_can_read_the_pdf(client, app):
    sid, d = make_draft(client, {})
    url = f"/api/v1/drafts/{d['draft_id']}/pdf"
    assert client.get(url).status_code == 403  # no session
    other_sid, _ = make_draft(client, {})
    assert client.get(url, headers=owner(other_sid)).status_code == 403  # someone else's session
    assert client.get(url, headers=staff("reviewer")).status_code == 403  # not shared yet
    assert client.get(url, headers=staff("reviewer", aal="aal1")).json["error"]["code"] == "MFA_REQUIRED"
    assert client.get(url, headers=staff("operator")).status_code == 403  # operators are not reviewers
    assert client.get("/api/v1/drafts/DRF_nope/pdf", headers=owner(sid)).status_code == 404
    assert client.get(url, headers=owner(sid)).status_code == 200
    r = client.post(f"/api/v1/drafts/{d['draft_id']}/handoff", json={"consent": {"share_with_reviewer": True}},
                    headers={"X-Session-Id": sid, "Idempotency-Key": uuid.uuid4().hex})
    assert r.status_code == 201
    for role in ("reviewer", "admin"):
        got = client.get(url, headers=staff(role))
        assert got.status_code == 200 and got.data[:5] == b"%PDF-"
    assert client.get(url, headers=staff("operator")).status_code == 403


def test_signed_in_citizens_draft_is_closed_to_other_accounts(client):
    mine, theirs = bearer(token(str(uuid.uuid4()), email="a@example.org")), bearer(token(str(uuid.uuid4()), email="b@example.org"))
    sid, d = make_draft(client, mine)
    url = f"/api/v1/drafts/{d['draft_id']}/pdf"
    assert client.get(url, headers={**mine, "X-Session-Id": sid}).status_code == 200
    assert client.get(url, headers={**theirs, "X-Session-Id": sid}).status_code == 403
    assert client.get(url, headers={"X-Session-Id": sid}).status_code == 403


def test_kiosk_draft_is_bound_to_device_and_operator(client):
    h = kiosk()
    sid, d = make_draft(client, h, mode="kiosk")
    url = f"/api/v1/drafts/{d['draft_id']}/helper"
    assert client.get(url, headers=owner(sid, h)).status_code == 200
    assert client.get(url, headers=owner(sid, kiosk(device="KD-another-kiosk-9"))).status_code == 403


def test_pdf_downloads_are_audited_without_values(app, client):
    from anvaya.db import connect
    sid, d = make_draft(client, {})
    client.get(f"/api/v1/drafts/{d['draft_id']}/pdf?language=hi", headers=owner(sid))
    db = connect(app.config)
    try:
        rows = db.execute("SELECT details_json FROM audit_events WHERE action='draft.pdf_downloaded' AND session_id=?", (sid,)).fetchall()
    finally:
        db.close()
    assert len(rows) == 1 and "Lakshmi" not in rows[0][0] and '"language": "hi"' in rows[0][0]


# ---------------------------------------------------------------- no Aadhaar / bank numbers

def test_no_aadhaar_or_bank_numbers_in_the_pdf_or_the_view(client):
    nasty = "Lakshmi 1234 5678 9012 acct 000123456789"
    sid, d = make_draft(client, {}, name=nasty)
    view = client.get(f"/api/v1/drafts/{d['draft_id']}/helper", headers=owner(sid)).json
    name_field = next(f for f in view["fields"] if f["key"] == "applicant_name")
    assert not re.search(r"\d{4}\s?\d{4}\s?\d{4}|\d{9,}", name_field["value"]) and "Lakshmi" in name_field["value"]
    for lang in ("en", "hi", "te"):
        text = pdf_text(client.get(f"/api/v1/drafts/{d['draft_id']}/pdf?language={lang}", headers=owner(sid)).data)
        digits = re.sub(r"[\s-]", "", text)
        assert not re.search(r"[0-9]{9,}", digits)
        assert "123456789012" not in digits and "000123456789" not in digits and "1234 5678 9012" not in text
    office = {o["key"] for o in view["office_only"]}
    assert office == {"aadhaar_number", "bank_account"}


def test_the_mask_and_dataset_filters():
    assert "123456789012" not in formhelper.mask_citizen_value("id 1234-5678-9012 end", "en")
    assert formhelper.mask_citizen_value("age 67, 2 acres", "en") == "age 67, 2 acres"
    assert formhelper.mask_dataset_text("call 1800-180-1111 or Aadhaar 1234 5678 9012") == "call 1800-180-1111 or Aadhaar XXXX XXXX XXXX"


# ---------------------------------------------------------------- copy-ready view

def test_fields_are_in_form_order_missing_ones_say_what_to_bring(client):
    sid, d = make_draft(client, {}, name=None)
    v = client.get(f"/api/v1/drafts/{d['draft_id']}/helper", headers=owner(sid)).json
    keys = [f["key"] for f in v["fields"]]
    order = {k: i for i, k in enumerate(formhelper.FORM_ORDER)}
    assert keys == sorted(keys, key=lambda k: (order.get(k, 99), k))
    name = next(f for f in v["fields"] if f["key"] == "applicant_name")
    assert name["tag"] == "missing" and name["value"] is None and name["copy_text"] is None and name["bring"]
    state = next(f for f in v["fields"] if f["key"] == "state")
    assert state["tag"] == "confirmed" and state["copy_text"] == "Andhra Pradesh"
    age = next(f for f in v["fields"] if f["key"] == "age")
    assert age["copy_text"] == "67 years"
    hint = " ".join(o["hint"] for o in v["office_only"])
    assert "Provide at the office" in hint and "never asks" in hint


def test_helper_in_hindi_and_telugu_labels(client):
    sid, d = make_draft(client, {})
    for lang, label in (("hi", "आवेदक का नाम"), ("te", "దరఖాస్తుదారుని పేరు")):
        v = client.get(f"/api/v1/drafts/{d['draft_id']}/helper?language={lang}", headers=owner(sid)).json
        assert next(f for f in v["fields"] if f["key"] == "applicant_name")["label"] == label
    assert client.get(f"/api/v1/drafts/{d['draft_id']}/helper?language=fr", headers=owner(sid)).status_code == 422


# ---------------------------------------------------------------- steps, link, QR

def test_steps_are_a_numbered_list_machine_translated_and_labelled(client, fake_translation):
    sid, d = make_draft(client, {})
    en = client.get(f"/api/v1/drafts/{d['draft_id']}/helper?language=en", headers=owner(sid)).json
    assert en["steps"] and not any(s["machine_translated"] for s in en["steps"]) and not en["steps_machine_translated"]
    hi = client.get(f"/api/v1/drafts/{d['draft_id']}/helper?language=hi", headers=owner(sid)).json
    assert hi["steps_machine_translated"] and all(s["machine_translated"] and s["text"].startswith("आवेदन चरण") for s in hi["steps"])
    assert [s["text_en"] for s in hi["steps"]] == [s["text"] for s in en["steps"]]
    assert hi["labels"]["mt"] == "मशीन अनुवाद"
    text = squash(pdf_text(client.get(f"/api/v1/drafts/{d['draft_id']}/pdf?language=hi", headers=owner(sid)).data))
    assert squash("मशीन अनुवाद") in text


def test_steps_fall_back_to_english_when_translation_is_unavailable(client, monkeypatch):
    monkeypatch.setattr(translation, "translate_many", lambda texts, s, t: {})
    sid, d = make_draft(client, {})
    v = client.get(f"/api/v1/drafts/{d['draft_id']}/helper?language=te", headers=owner(sid)).json
    assert v["steps"] and not v["steps_machine_translated"] and v["steps_note"]
    assert all(s["text"] == s["text_en"] for s in v["steps"])


def test_parse_steps_cleans_the_dataset_text():
    steps = formhelper.parse_steps("Process 1:\n\n1. Open the form �\n1. Submit at the block office.\n"
                                   "Step 3: Keep the receipt [https://x.gov.in/a]()\n")
    assert [(s["heading"], s["text"]) for s in steps] == [
        (True, "Process 1:"), (False, "Open the form"), (False, "Submit at the block office."),
        (False, "Keep the receipt https://x.gov.in/a")]
    assert formhelper.parse_steps(None) == [] and formhelper.parse_steps("") == []


def test_official_link_and_qr_code(client):
    sid, d = make_draft(client, {})
    v = client.get(f"/api/v1/drafts/{d['draft_id']}/helper", headers=owner(sid)).json
    link = v["official_link"]
    assert link and re.fullmatch(r"https?://\S+", link["url"]) and v["qr_url"] == f"/api/v1/schemes/{v['scheme_id']}/portal-qr.svg"
    qr = client.get(v["qr_url"])
    assert qr.status_code == 200 and qr.mimetype == "image/svg+xml" and qr.data.lstrip().startswith(b"<svg")
    assert link["url"] in squash_free(pdf_text(client.get(f"/api/v1/drafts/{d['draft_id']}/pdf", headers=owner(sid)).data))
    assert client.get("/api/v1/schemes/nope/portal-qr.svg").status_code == 404


def squash_free(text: str) -> str:
    return re.sub(r"\s", "", text)


# ---------------------------------------------------------------- case code, wording

def test_case_code_appears_only_when_the_citizen_offers_the_matching_code(client):
    sid, d = make_draft(client, {})
    r = client.post(f"/api/v1/drafts/{d['draft_id']}/handoff", json={"consent": {"share_with_reviewer": True}},
                    headers={"X-Session-Id": sid, "Idempotency-Key": uuid.uuid4().hex}).json
    url = f"/api/v1/drafts/{d['draft_id']}/helper"
    assert client.get(url, headers=owner(sid)).json["case"]["code"] is None
    wrong = client.get(url, headers={**owner(sid), "X-Case-Code": "ANV-ZZZZ-ZZZZ"}).json["case"]["code"]
    assert wrong is None
    got = client.get(url, headers={**owner(sid), "X-Case-Code": r["code"]}).json["case"]
    assert got["code"] == r["code"] and got["case_id"] == r["case_id"]
    pdf = client.get(f"/api/v1/drafts/{d['draft_id']}/pdf", headers={**owner(sid), "X-Case-Code": r["code"]}).data
    assert squash(r["code"]) in squash(pdf_text(pdf))


def test_draft_status_wording_never_says_submitted_or_applied():
    from anvaya import i18n
    for lang, label in i18n.CASE_STATUS["DRAFT_SAVED"].items():
        assert "ready" in label.lower() or lang != "en"
        assert "submitted" not in label.lower() and "applied" not in label.lower()
    assert i18n.CASE_STATUS["DRAFT_SAVED"]["en"] == "Draft ready — submit at the office/portal"
