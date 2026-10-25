// Browser checks for the landing page and sign-in (not part of CI: needs Playwright + Chromium and a running app).
//   npm run build && (cd ../backend && python -m anvaya ...)   # or any server on BASE
//   BASE=http://127.0.0.1:5000 node e2e/landing-check.mjs
// Checks: rotation order, CLS = 0 across one full rotation (PerformanceObserver), manifest icons resolve (200),
// "coming_soon" sign-in buttons fire no request, kiosk hides DigiLocker/phone. Screenshots go to e2e/screenshots/.
import { mkdirSync } from "node:fs";
import { createRequire } from "node:module";

// Resolved like require(), so a globally installed Playwright works (NODE_PATH=$(npm root -g)).
const { chromium } = createRequire(import.meta.url)("playwright");

const BASE = process.env.BASE || "http://127.0.0.1:5000";
const OUT = new URL("./screenshots/", import.meta.url).pathname;
mkdirSync(OUT, { recursive: true });
const fail = [];
const check = (ok, msg) => { console.log(`${ok ? "PASS" : "FAIL"} ${msg}`); if (!ok) fail.push(msg); };

const browser = await chromium.launch();
for (const [w, h] of [[1440, 900], [390, 844]]) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h } });
  await ctx.addInitScript(() => {
    try { sessionStorage.setItem("anvaya.lang", "en"); } catch { /* */ }
    window.__cls = 0;
    new PerformanceObserver((l) => { for (const e of l.getEntries()) if (!e.hadRecentInput) window.__cls += e.value; })
      .observe({ type: "layout-shift", buffered: true });
  });
  const p = await ctx.newPage();
  await p.goto(`${BASE}/`, { waitUntil: "networkidle" });
  await p.evaluate(() => document.fonts.ready);
  await p.waitForTimeout(1000);
  const cls0 = await p.evaluate(() => window.__cls);
  const order = [];
  for (let i = 0; i <= 4; i++) {
    order.push(await p.evaluate(() => document.querySelector('.hl-line[data-state="in"]')?.dataset.line));
    if (i < 4) await p.waitForTimeout(3820);
  }
  const seq = ["hinglish", "hi", "en", "te"], start = seq.indexOf(order[0]);
  check(order.every((id, i) => id === seq[(start + i) % 4]), `${w}px rotation order ${order.join(" → ")}`);
  const cls = (await p.evaluate(() => window.__cls)) - cls0;
  check(cls === 0, `${w}px CLS across one full rotation = ${cls}`);
  for (const [label, id] of [["Hinglish", "hinglish"], ["हिंदी", "hi"], ["English", "en"], ["తెలుగు", "te"]]) {
    await p.locator(".hl-langs").getByRole("button", { name: label, exact: true }).click();
    await p.mouse.move(2, 2);
    await p.waitForTimeout(900);
    await p.screenshot({ path: `${OUT}hero-${w}-${id}.png` });
  }
  check(await p.evaluate(() => document.documentElement.lang) === "te", `${w}px clicking తెలుగు switches the UI language`);

  const manifest = await (await p.request.get(`${BASE}/manifest.webmanifest`)).json();
  for (const icon of manifest.icons) check((await p.request.get(`${BASE}${icon.src}`)).status() === 200, `icon ${icon.src} 200`);

  await p.goto(`${BASE}/signin`, { waitUntil: "networkidle" });
  const fired = [];
  p.on("request", (r) => { if (/\/auth\/(digilocker|phone)/.test(r.url())) fired.push(r.url()); });
  const cfg = await (await p.request.get(`${BASE}/api/config`)).json();
  if (cfg.digilocker_status === "coming_soon") {
    await p.getByRole("button", { name: /Meri Pehchaan/ }).click({ force: true });
    await p.getByRole("button", { name: /phone OTP/ }).click({ force: true });
    await p.waitForTimeout(300);
    check(fired.length === 0, `${w}px coming_soon buttons fire no request`);
  }
  await p.screenshot({ path: `${OUT}signin-${cfg.digilocker_status}-${w}.png`, fullPage: true });
  await p.evaluate(() => sessionStorage.setItem("anvaya.mode", "kiosk"));
  await p.reload({ waitUntil: "networkidle" });
  check((await p.getByText(/Meri Pehchaan|phone OTP/).count()) === 0, `${w}px kiosk hides DigiLocker and phone`);
  await ctx.close();
}
await browser.close();
if (fail.length) { console.error(`${fail.length} check(s) failed`); process.exit(1); }
