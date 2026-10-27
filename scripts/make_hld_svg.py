#!/usr/bin/env python
"""Draw the high-level-design diagram as an SVG (and a PNG through Chrome), with every box and arrow placed by hand.

Mermaid's automatic layout sends long lines across a diagram with this many parts, so the README's picture is drawn here instead and the
Mermaid version (docs/diagrams/hld.mmd) is kept as an editable fallback. Layers, top to bottom: the browser, the Flask API, the data;
optional services, planned items and operations sit in a column on the right. Solid lines are built and used; dotted lines are optional or planned.

    backend/.venv/Scripts/python.exe scripts/make_hld_svg.py          # writes docs/diagrams/hld.svg and hld.png (PNG needs playwright + Chrome)
"""
from __future__ import annotations

from html import escape
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "docs" / "diagrams"
W, H = 1520, 830

PALETTE = {  # fill, stroke, text
    "edge": ("#e3eef9", "#155e9c", "#10243a"), "api": ("#e2f3e6", "#1f7a3a", "#10281a"), "data": ("#efe6f8", "#6b3fa0", "#241338"),
    "ext": ("#fdf0d6", "#9a5b00", "#33270f"), "ops": ("#eceeed", "#5f6966", "#1d2422"), "soon": ("#ffffff", "#8a8f8d", "#4b5653"),
}
BAND = {"edge": "#f3f8fd", "api": "#f4faf5", "data": "#f8f4fc", "ext": "#fffaf0", "ops": "#f6f7f6", "soon": "#fcfcfc"}
parts: list[str] = []


def band(x, y, w, h, title, kind, dashed=False, tx=18):
    stroke = PALETTE[kind][1]
    parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="16" fill="{BAND[kind]}" stroke="{stroke}" stroke-width="1.5"'
                 f'{" stroke-dasharray=\'6 5\'" if dashed else ""}/>')
    parts.append(f'<text x="{x + tx}" y="{y + 26}" class="band" fill="{stroke}">{escape(title)}</text>')


def box(x, y, w, h, title, lines, kind, dashed=False, cyl=False):
    fill, stroke, text = PALETTE[kind]
    dash = ' stroke-dasharray="5 4"' if dashed else ""
    if cyl:
        parts.append(f'<path d="M{x} {y + 12} v{h - 24} a{w / 2} 12 0 0 0 {w} 0 v-{h - 24} a{w / 2} 12 0 0 0 -{w} 0 a{w / 2} 12 0 0 0 {w} 0" '
                     f'fill="{fill}" stroke="{stroke}" stroke-width="1.6"/>')
    else:
        parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="{fill}" stroke="{stroke}" stroke-width="1.6"{dash}/>')
    n = 1 + len(lines)
    top = y + h / 2 - (n - 1) * 10 + (6 if cyl else 0)
    parts.append(f'<text x="{x + w / 2}" y="{top}" text-anchor="middle" class="title" fill="{text}">{escape(title)}</text>')
    for i, ln in enumerate(lines, 1):
        parts.append(f'<text x="{x + w / 2}" y="{top + i * 20}" text-anchor="middle" class="sub" fill="{text}">{escape(ln)}</text>')


def arrow(d, color="#4b5653", dashed=False, label=None, lx=None, ly=None):
    dash = ' stroke-dasharray="6 5"' if dashed else ""
    parts.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="2"{dash} marker-end="url(#a)"/>')
    if label:
        w = 7.2 * len(label) + 14
        parts.append(f'<rect x="{lx - w / 2}" y="{ly - 13}" width="{w}" height="22" rx="6" fill="#ffffff" stroke="#d9dedc"/>')
        parts.append(f'<text x="{lx}" y="{ly + 3}" text-anchor="middle" class="lbl" fill="#3a4441">{escape(label)}</text>')


# ------------------------------------------------------------------------------------------ left column: browser, API, data
band(20, 20, 1040, 150, "Browser and kiosk PWA (React + Vite)", "edge")
box(50, 62, 300, 84, "Citizen · Kiosk operator", ["Reviewer · Admin", "three languages"], "edge")
box(400, 62, 300, 84, "Voice in and out", ["VerbX → browser speech → typing"], "edge")
box(750, 62, 290, 84, "Offline pre-screen", ["cached rule bundle + outbox"], "edge")

band(20, 215, 1040, 365, "Flask API (gunicorn, 1 worker × 8 threads)", "api", tx=330)
box(50, 255, 250, 84, "Auth", ["JWT checked on every request", "TOTP for staff"], "api")
box(370, 255, 300, 84, "Conversation", ["rules extractor + optional LLM", "always confirmed by the citizen"], "api")
box(750, 255, 290, 84, "Offline sync", ["dedupe + re-check"], "api")
box(370, 400, 300, 74, "Rules engine", ["pure · versioned · quoted"], "api")
box(750, 400, 290, 74, "Catalogue", ["3,534 schemes · 17 reviewed rules"], "api")
box(50, 400, 250, 74, "Documents · Jobs", ["signed links · retention · limits"], "api")
box(370, 505, 300, 62, "Drafts · Form Helper", ["cases · review · audit"], "api")

band(20, 625, 1040, 160, "Data: Supabase", "data")
box(50, 665, 250, 96, "Supabase Auth", ["anonymous · email OTP", "password + TOTP"], "data")
box(370, 665, 250, 96, "Postgres", ["RLS on, no policies"], "data", cyl=True)
box(690, 665, 250, 96, "Private Storage", ["documents, signed links"], "data", cyl=True)

# flows inside the left column
arrow("M200 146 V255", label="HTTPS + JWT", lx=200, ly=193)
arrow("M300 297 H370")                                         # auth -> conversation
arrow("M520 339 V400")                                         # conversation -> rules
arrow("M895 339 V366 H600 V400", label="re-check", lx=748, ly=366)   # sync -> rules
arrow("M895 146 V255", label="offline events", lx=895, ly=193)       # offline -> sync
arrow("M750 437 H670")                                         # catalogue -> rules
arrow("M520 474 V505")                                         # rules -> drafts
arrow("M520 567 V665", label="", lx=520, ly=620)               # drafts -> postgres
arrow("M175 474 V600 H455 V665")                               # documents -> postgres
arrow("M175 474 V592 H815 V665")                               # documents -> storage
arrow("M50 297 H34 V713 H50", dashed=True, label="verify", lx=34, ly=500)   # auth -> supabase auth

# ------------------------------------------------------------------------------------------ right column
band(1100, 20, 400, 300, "Optional services (each has a fallback)", "ext", dashed=True)
for i, (t, s) in enumerate([("VerbX", "speech · translate"), ("Groq → Gemini", "candidate facts only"), ("Langfuse", "LLM traces"), ("Cloudflare Turnstile", "CAPTCHA")]):
    box(1130, 60 + i * 61, 340, 52, t, [s], "ext", dashed=True)
band(1100, 345, 400, 130, "Planned", "soon", dashed=True)
box(1130, 380, 160, 70, "DigiLocker", ["Meri Pehchaan"], "soon", dashed=True)
box(1310, 380, 160, 70, "API Setu", ["live scheme data"], "soon", dashed=True)
band(1100, 500, 400, 120, "Operations", "ops")
box(1130, 535, 130, 66, "GitHub Actions", ["hourly jobs"], "ops")
box(1280, 535, 100, 66, "Prometheus", [], "ops")
box(1400, 535, 80, 66, "Grafana", [], "ops")
arrow("M1380 568 H1400", color="#5f6966")


parts.append('<text x="1118" y="338" class="lbl" fill="#3a4441"></text>')
# legend
parts.append('<line x1="1100" y1="680" x2="1150" y2="680" stroke="#4b5653" stroke-width="2" marker-end="url(#a)"/><text x="1160" y="685" class="lbl" fill="#3a4441">built and used</text>')
parts.append('<line x1="1100" y1="710" x2="1150" y2="710" stroke="#9a5b00" stroke-width="2" stroke-dasharray="6 5" marker-end="url(#a)"/>'
             '<text x="1160" y="715" class="lbl" fill="#3a4441">optional (degrades gracefully) or planned</text>')
parts.append('<text x="1100" y="755" class="lbl" fill="#3a4441">Supabase is used for sign-in and storage only; the browser</text>'
             '<text x="1100" y="775" class="lbl" fill="#3a4441">never talks to the database directly.</text>')

svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" '
       f'aria-label="Anvaya AI high-level design: browser, Flask API, Supabase data, optional services, planned items and operations">'
       '<style>text{font-family:"Segoe UI","Noto Sans",Arial,sans-serif}.band{font-size:15px;font-weight:700}.title{font-size:16px;font-weight:700}'
       '.sub{font-size:13.5px}.lbl{font-size:12px}</style>'
       '<defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">'
       '<path d="M0 0 L10 5 L0 10 z" fill="context-stroke"/></marker></defs>'
       f'<rect width="{W}" height="{H}" fill="#ffffff"/>' + "".join(parts) + "</svg>")
OUT.mkdir(parents=True, exist_ok=True)
(OUT / "hld.svg").write_text(svg, encoding="utf-8")
print("wrote", OUT / "hld.svg")

try:  # the PNG is what the README shows; it needs Chrome through playwright
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome")
        page = b.new_page(viewport={"width": W, "height": H}, device_scale_factor=2)
        page.goto((OUT / "hld.svg").as_uri())
        page.screenshot(path=str(OUT / "hld.png"))
        b.close()
    print("wrote", OUT / "hld.png")
except Exception as e:  # noqa: BLE001
    print("PNG not written:", e)
