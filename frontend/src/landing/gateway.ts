// "Gateway": speech fragments in many Indian languages travel along dotted curves from both edges, shrink, turn
// marigold and merge into one point (the mic). Each arrival feeds a glow at the centre. Click to scatter them.

const FAM = 'Inter, "Noto Sans Devanagari", "Noto Sans Bengali", "Noto Sans Tamil", "Noto Sans Telugu", "Noto Sans Gujarati", "Noto Sans Gurmukhi", "Noto Sans Kannada", "Noto Sans Malayalam", "Noto Sans Oriya", "Noto Sans Arabic", sans-serif';

// [text, highlighted]: highlighted fragments carry an eligibility fact (age, land, pension…).
const WORDS: [string, boolean][] = [
  ["umar 58", true], ["kheti", false], ["do acre", true], ["Gaya, Bihar", true], ["pension nahi", false], ["BPL card", false],
  ["beti ki padhai", false], ["mazdoori", false], ["ration card", false], ["vidhwa", false], ["ghar kachcha hai", false],
  ["matlab…", false], ["haan toh", false],
  ["किसान", false], ["पेंशन", true], ["राशन कार्ड", false], ["बेटी की पढ़ाई", false], ["विधवा", false], ["दो एकड़", true],
  ["उम्र 58", true], ["मज़दूरी", false], ["दिव्यांग", false],
  ["কৃষক", false], ["বয়স্ক ভাতা", true], ["রেশন কার্ড", false], ["ছাত্রী", false],
  ["விவசாயி", false], ["ஓய்வூதியம்", true], ["மாணவி", false],
  ["రైతు", false], ["పింఛను", true], ["రెండు ఎకరాలు", true], ["గుంటూరు", false],
  ["शेतकरी", false], ["ખેડૂત", false], ["વિધવા સહાય", true], ["ਕਿਸਾਨ", false], ["ਪੈਨਸ਼ਨ", true], ["ರೈತ", false],
  ["ವಿದ್ಯಾರ್ಥಿ", false], ["കർഷകൻ", false], ["କୃଷକ", false], ["کسان", false],
  ["farmer", false], ["widow", false], ["student", false], ["daily wage", false], ["2 acres", true], ["no pension", false],
  ["age 58", true], ["disability", false], ["self-employed", false],
];

type Word = { t: number; v: number; s: string; hi: boolean };
type Path = { left: boolean; base: number; y: number; size: number; ps: Word[] };
type Burst = { x: number; y: number; r: number; life: number };

export type GatewayOptions = { speed?: number; density?: number; reduced?: boolean };

export function startGateway(cv: HTMLCanvasElement, opts: GatewayOptions = {}) {
  const ctx = cv.getContext("2d");
  const noop = { burst: (_x: number, _y: number) => undefined, burstCenter: () => undefined, setVisible: (_v: boolean) => undefined, destroy: () => undefined };
  if (!ctx) return noop;
  const c = ctx;
  const R = Math.random;
  const speed = opts.speed ?? 1, density = opts.density ?? 1, reduced = !!opts.reduced;
  const pickWord = () => WORDS[(R() * WORDS.length) | 0];
  // Performance (mid-range Android, 4× CPU throttle): the dotted curves are drawn once into an offscreen layer, and
  // each word is shaped once into a sprite that is then scaled down; nothing is re-shaped per frame.
  const layer = document.createElement("canvas");
  const sprites = new Map<string, { c: HTMLCanvasElement; w: number; h: number }>();
  const sprite = (text: string, size: number, color: string) => {
    const key = `${text}|${size}|${color}`;
    let sp = sprites.get(key);
    if (!sp) {
      const k = st.dpr, m = document.createElement("canvas").getContext("2d")!;
      m.font = `500 ${size}px ${FAM}`;
      const w = Math.ceil(m.measureText(text).width) + 4, h = Math.ceil(size * 1.6);
      const cvs = document.createElement("canvas");
      cvs.width = w * k; cvs.height = h * k;
      const x = cvs.getContext("2d")!;
      x.scale(k, k); x.font = `500 ${size}px ${FAM}`; x.fillStyle = color; x.textBaseline = "middle"; x.fillText(text, 2, h / 2);
      sp = { c: cvs, w, h };
      if (sprites.size > 1500) sprites.clear();
      sprites.set(key, sp);
    }
    return sp;
  };
  const drawLayer = () => {
    const { W, H } = st, cx = W / 2, cy = H / 2;
    layer.width = Math.round(W * st.dpr); layer.height = Math.round(H * st.dpr);
    const l = layer.getContext("2d")!;
    l.setTransform(st.dpr, 0, 0, st.dpr, 0, 0);
    l.setLineDash([1, 5]); l.lineWidth = 1; l.strokeStyle = "rgba(250,247,242,0.17)";
    for (const p of st.paths) {
      const x0 = p.left ? 0 : W, x1 = p.left ? cx * 0.5 : W - cx * 0.5, x2 = p.left ? cx * 0.8 : W - cx * 0.8;
      l.beginPath(); l.moveTo(x0, p.y); l.bezierCurveTo(x1, p.y, x2, cy, cx, cy); l.stroke();
    }
  };

  const st = { W: 0, H: 0, dpr: 1, paths: [] as Path[], bursts: [] as Burst[], pulses: [] as { r: number; a: number }[], energy: 0, visible: true, last: 0, raf: 0 };
  const mkWord = (t: number): Word => { const w = pickWord(); return { t, v: 0.000052 + R() * 0.00005, s: w[0], hi: w[1] }; };

  const build = () => {
    const narrow = st.W < 700;
    const n = Math.max(8, Math.min(40, Math.round((st.H / 24) * density * (narrow ? 0.6 : 1))));
    st.paths = [];
    for (let side = 0; side < 2; side++) {
      for (let i = 0; i < n; i++) {
        const base = (i / (n - 1)) * st.H * 1.4 - st.H * 0.2;
        const ps = [mkWord(R())];
        if (R() < 0.35) ps.push(mkWord((ps[0].t + 0.5) % 1));
        st.paths.push({ left: side === 0, base, y: base + (R() - 0.5) * 16, size: (11 + R() * 8) * (narrow ? 0.78 : 1), ps });
      }
    }
  };
  const bz = (t: number, a: number, b: number, cc: number, d: number) => { const u = 1 - t; return u * u * u * a + 3 * u * u * t * b + 3 * u * t * t * cc + t * t * t * d; };
  const dbz = (t: number, a: number, b: number, cc: number, d: number) => { const u = 1 - t; return 3 * u * u * (b - a) + 6 * u * t * (cc - b) + 3 * t * t * (d - cc); };

  const frame = (dt: number) => {
    const { W, H } = st;
    const cx = W / 2, cy = H / 2;
    c.setTransform(st.dpr, 0, 0, st.dpr, 0, 0);
    c.clearRect(0, 0, W, H);

    st.energy *= Math.pow(0.9982, dt);
    const e = Math.min(st.energy, 40);
    const gr = 70 + e * 3.2;
    const g = c.createRadialGradient(cx, cy, 0, cx, cy, gr);
    g.addColorStop(0, `rgba(232,131,58,${(0.22 + e * 0.009).toFixed(3)})`);
    g.addColorStop(1, "rgba(232,131,58,0)");
    c.fillStyle = g; c.fillRect(cx - gr, cy - gr, gr * 2, gr * 2);

    c.drawImage(layer, 0, 0, W, H);

    for (const b of st.bursts) { b.r += dt * 0.9; b.life -= dt * 0.0009; }
    st.bursts = st.bursts.filter((b) => b.life > 0);

    for (const p of st.paths) {
      const x0 = p.left ? 0 : W, x1 = p.left ? cx * 0.5 : W - cx * 0.5, x2 = p.left ? cx * 0.8 : W - cx * 0.8;
      for (const q of p.ps) {
        q.t += q.v * dt * speed;
        if (q.t >= 1) {
          const nw = pickWord();
          q.t -= 1; q.s = nw[0]; q.hi = nw[1]; q.v = 0.000052 + R() * 0.00005;
          st.energy += 1;
          if (R() < 0.22) st.pulses.push({ r: 44, a: 0.55 });
        }
        const t = q.t;
        let x = bz(t, x0, x1, x2, cx), y = bz(t, p.y, p.y, cy, cy);
        for (const b of st.bursts) {
          const dx = x - b.x, dy = y - b.y, d = Math.hypot(dx, dy) || 1;
          const band = Math.abs(d - b.r);
          if (band < 120) { const f = (1 - band / 120) * b.life; x += (dx / d) * f * 70; y += (dy / d) * f * 70; }
        }
        const fadeIn = Math.min(1, t / 0.05);
        const textA = t < 0.8 ? 1 : Math.max(0, (0.9 - t) / 0.1);
        if (textA > 0.01) {
          const fs = Math.max(4, p.size * Math.pow(1 - t, 0.62));
          let ang = Math.atan2(dbz(t, p.y, p.y, cy, cy), dbz(t, x0, x1, x2, cx));
          if (!p.left) ang += Math.PI;
          ang = Math.atan2(Math.sin(ang), Math.cos(ang)) * 0.9;
          const base = Math.round(p.size);
          const sp = sprite(q.s, base, q.hi || t > 0.62 ? "#F2A766" : "#FAF7F2");
          const k = fs / base;
          c.save(); c.translate(x, y); c.rotate(ang);
          c.globalAlpha = fadeIn * textA * (q.hi ? 1 : 0.8);
          // text trails behind its leading point: right-aligned on the left side, left-aligned on the right
          c.drawImage(sp.c, p.left ? -sp.w * k : 0, (-sp.h * k) / 2, sp.w * k, sp.h * k);
          c.restore();
        }
        if (t > 0.78) {
          c.globalAlpha = Math.min(1, (t - 0.78) / 0.08);
          c.fillStyle = "#F2A766"; c.fillRect(x - 1.4, y - 1.4, 2.8, 2.8);
          c.globalAlpha = 1;
        }
      }
    }
    c.globalAlpha = 1;
    for (const pu of st.pulses) { pu.r += dt * 0.05; pu.a -= dt * 0.00045; }
    st.pulses = st.pulses.filter((pu) => pu.a > 0);
    c.lineWidth = 1;
    for (const pu of st.pulses) { c.beginPath(); c.arc(cx, cy, pu.r, 0, Math.PI * 2); c.strokeStyle = `rgba(232,131,58,${pu.a.toFixed(3)})`; c.stroke(); }
  };

  const resize = () => {
    const W = cv.clientWidth, H = cv.clientHeight;
    if (!W || !H) return;
    st.dpr = Math.min(window.devicePixelRatio || 1, W < 700 ? 1.5 : 2);
    cv.width = Math.round(W * st.dpr); cv.height = Math.round(H * st.dpr);
    const rebuild = Math.abs(W - st.W) > 40 || Math.abs(H - st.H) > 40 || !st.paths.length;
    st.W = W; st.H = H;
    if (rebuild) build();
    sprites.clear();
    drawLayer();
    frame(0);
  };
  // Sprites shaped before the web fonts arrived used a fallback face: reshape once fonts load.
  const onFonts = () => sprites.clear();
  document.fonts?.addEventListener?.("loadingdone", onFonts);
  const ro = typeof ResizeObserver !== "undefined" ? new ResizeObserver(resize) : null;
  ro?.observe(cv);
  resize();
  if (!reduced) {
    st.last = performance.now();
    const loop = (now: number) => {
      const dt = Math.min(48, now - st.last);
      st.last = now;
      if (st.visible && st.W) frame(dt);
      st.raf = requestAnimationFrame(loop);
    };
    st.raf = requestAnimationFrame(loop);
  }
  return {
    burst: (x: number, y: number) => { st.bursts.push({ x, y, r: 0, life: 1 }); },
    burstCenter: () => { st.bursts.push({ x: st.W / 2, y: st.H / 2, r: 0, life: 1 }); st.energy += 12; },
    setVisible: (v: boolean) => { st.visible = v; st.last = performance.now(); },
    destroy: () => { cancelAnimationFrame(st.raf); ro?.disconnect(); document.fonts?.removeEventListener?.("loadingdone", onFonts); },
  };
}
