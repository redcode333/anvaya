#!/usr/bin/env python
"""Render a Mermaid diagram (.mmd) to SVG and PNG so the README can show a picture that looks the same everywhere.

GitHub draws Mermaid code blocks in a sandbox that is stricter than a normal browser, and a block that works locally can still show
as raw code there. The README therefore embeds the rendered image and keeps the Mermaid source underneath it, editable.

    backend/.venv/Scripts/python.exe -m pip install playwright        # once; Chrome must be installed; Mermaid is fetched from a CDN
    backend/.venv/Scripts/python.exe scripts/render_diagram.py docs/diagrams/hld.mmd
Writes docs/diagrams/hld.svg and docs/diagrams/hld.png next to the source.
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

MERMAID = "11.4.1"  # pinned, so the picture does not change when Mermaid does

src = Path(sys.argv[1]).resolve()
code = src.read_text(encoding="utf-8")
html = """<!doctype html><meta charset="utf-8"><body style="margin:0;background:#ffffff"><div id="out" style="display:inline-block;padding:24px"></div>
<script type="module">
import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@%s/dist/mermaid.esm.min.mjs';
mermaid.initialize({startOnLoad: false, securityLevel: 'strict', theme: 'base', fontFamily: 'Segoe UI, Noto Sans, Arial, sans-serif',
  themeVariables: {fontSize: '16px', primaryColor: '#f1ece2', lineColor: '#4b5653', clusterBkg: '#fafaf7', clusterBorder: '#c9c3b6'},
  flowchart: {htmlLabels: true, useMaxWidth: false, nodeSpacing: 36, rankSpacing: 56, curve: 'basis', padding: 14}});
window.render = async (code) => { const r = await mermaid.render('diagram', code); document.getElementById('out').innerHTML = r.svg; return r.svg; };
window.ready = true;
</script></body>""" % MERMAID
tmp = src.with_suffix(".render.html")
tmp.write_text(html, encoding="utf-8")
try:
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        page = browser.new_page(viewport={"width": 1800, "height": 1400}, device_scale_factor=2)
        page.goto(tmp.as_uri())
        page.wait_for_function("window.ready === true", timeout=60000)
        svg = page.evaluate("code => window.render(code)", code)
        if "Syntax error" in svg:
            raise SystemExit("Mermaid reported a syntax error in " + str(src))
        page.locator("#out").screenshot(path=str(src.with_suffix(".png")))
        src.with_suffix(".svg").write_text(svg, encoding="utf-8")
        browser.close()
finally:
    tmp.unlink(missing_ok=True)
print("wrote", src.with_suffix(".svg"), "and", src.with_suffix(".png"))
