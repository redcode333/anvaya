// Hand-drawn crowd of Indian citizens walking across the hero (canvas 2D, original line-art, no sprite sheet).
// Farmers in dhoti-kurta with pagdi or Gandhi topi, women in sarees and salwar-dupatta, elders with sticks,
// Sikh men in dastar, students, workers; T-shirts carry Indian names. Some ask about schemes in speech bubbles.

const INK = "#16181D";
const SKIN = ["#C68B59", "#A86B43", "#8D5A3B", "#D29A6A", "#B97A4E", "#7E4E31", "#DDAA80", "#9C6440"];
const BRIGHT = ["#E8833A", "#1F4E79", "#C2477A", "#2E7D4F", "#E9B949", "#8DB3D9", "#9E3B2F", "#6C4E9B", "#D94F3D", "#3E8E8A"];
const LIGHT = ["#FFFFFF", "#F3EBDD", "#FFFFFF", "#EAF0F6"];
const NM = ["RAJU", "ARJUN", "RAMESH", "IMRAN", "SURESH", "BABLU", "MUNNA", "ANAND", "JOSEPH", "VIKRAM", "रमेश", "अजय", "हरि", "TENZIN", "SALIM", "GOPAL", "DEEPAK", "KISHORE", "राजू", "BIRSA"];
const NF = ["SUNITA", "PRIYA", "KAVYA", "ANITA", "MEENA", "FATIMA", "LAKSHMI", "सीता", "पूजा", "GEETA", "ROSY", "RANI", "NEHA", "SHABNAM"];
const NK = ["CHOTU", "PINKY", "GOLU", "MUNNI", "BITTU", "छोटू"];
const SAY = [
  "pension kab milegi?", "बेटी की पढ़ाई का ख़र्च…", "ration card mein naam nahi", "বয়স্ক ভাতা পাব?",
  "ਮੈਨੂੰ ਪੈਨਸ਼ਨ ਮਿਲੇਗੀ?", "உதவித்தொகை உண்டா?", "kheti ke liye loan?", "ಮನೆ ಯೋಜನೆ ಇದೆಯಾ?",
  "gas connection chahiye", "मज़दूरी का कार्ड?", "పింఛను వస్తుందా?", "ఇంటి పథకం ఉందా?",
];
const FAM = 'Inter, "Noto Sans Devanagari", "Noto Sans Telugu", "Noto Sans Bengali", "Noto Sans Tamil", "Noto Sans Gurmukhi", "Noto Sans Kannada", sans-serif';

const R = Math.random;
const pick = <T,>(a: T[]): T => a[(R() * a.length) | 0];

type Lower = { type: "dhoti" | "lungi" | "saree"; c: string; d: number; pad: number; border?: string };
type Person = {
  skin: string; hf: number; f: boolean; kid: boolean; top: "tshirt" | "kurta" | "shirt" | "vest" | "saree"; topC: string;
  name: string; sleeve: number; legs: "pants" | "skin" | "none"; legC: string; legW: number; shoe: string; lower: Lower | null;
  hair: "short" | "grey" | "bald" | "bun" | "braid" | "pony" | "plaits" | "none"; hairC: string;
  head: "pagdi" | "topi" | "dastar" | "ghoonghat" | null; headC: string; kurtaLen: number;
  border: string; blouse: string; dupatta: string;
  face: { stache?: boolean; stacheC?: string; beard?: boolean; glasses?: boolean; wrinkles?: boolean; bindi?: boolean; tilak?: boolean; earring?: boolean; nath?: boolean; sindoor?: boolean };
  acc: { gamchha?: boolean; jhola?: boolean; stick?: boolean; phone?: boolean; matka?: boolean; bag?: boolean };
};
type Walker = { p: Person; z: number; dir: 1 | -1; sp: number; ph: number; x: number };
type Bubble = { q: Walker; text: string; t0: number; life: number };

function textOn(bg: string) {
  const c = parseInt(bg.slice(1), 16);
  const r = (c >> 16) & 255, g = (c >> 8) & 255, b = c & 255;
  return 0.299 * r + 0.587 * g + 0.114 * b > 150 ? INK : "#FFFFFF";
}

function make(): Person {
  const roll = R();
  const p: Person = {
    skin: pick(SKIN), hf: 1, f: false, kid: false, top: "tshirt", topC: "#FFFFFF", name: "", sleeve: 0.32, legs: "pants",
    legC: "#3E5C84", legW: 0, shoe: INK, lower: null, hair: "short", hairC: INK, head: null, headC: "#E8833A", kurtaLen: 0,
    border: "#E9B949", blouse: "#E9B949", dupatta: "", face: {}, acc: {},
  };
  if (roll < 0.16) {
    p.top = "kurta"; p.topC = pick(["#FFFFFF", "#F3EBDD", "#EAF0F6"]); p.sleeve = 0.82; p.kurtaLen = 30;
    p.legs = "skin"; p.lower = { type: "dhoti", c: "#FFFFFF", d: 64, pad: 6 };
    p.head = pick(["pagdi", "pagdi", "topi", null] as Person["head"][]); p.headC = pick(["#E8833A", "#D94F3D", "#E9B949", "#FFFFFF", "#C2477A"]);
    p.face = { stache: true, tilak: R() < 0.3 }; p.acc = { gamchha: R() < 0.65 }; p.shoe = "#7A5230";
  } else if (roll < 0.27) {
    p.top = pick(["shirt", "vest"] as const); p.topC = pick(["#8DB3D9", "#FFFFFF", "#E9B949", "#3E8E8A"]); p.sleeve = p.top === "shirt" ? 0.32 : 0;
    p.legs = "skin"; p.lower = { type: "lungi", c: pick(["#1F4E79", "#2E7D4F", "#9E3B2F", "#6C4E9B"]), d: 66, pad: 5 };
    p.face = { stache: R() < 0.8 }; p.acc = { gamchha: R() < 0.35, jhola: R() < 0.2 }; p.shoe = "#7A5230";
  } else if (roll < 0.43) {
    p.top = "tshirt"; p.topC = pick(BRIGHT.concat(LIGHT)); p.name = pick(NM);
    p.legC = pick(["#3E5C84", "#2B3446", "#5A5048", "#B9A57A"]);
    p.face = { stache: R() < 0.3, glasses: R() < 0.15 }; p.acc = { phone: R() < 0.35, jhola: R() < 0.12 };
  } else if (roll < 0.51) {
    p.hf = 0.95; p.top = "kurta"; p.topC = pick(["#FFFFFF", "#F3EBDD"]); p.sleeve = 0.82; p.kurtaLen = 36;
    p.legC = "#FFFFFF"; p.hair = pick(["bald", "grey"] as const); p.head = R() < 0.5 ? "topi" : null;
    p.face = { stache: true, stacheC: "#D8D2C6", glasses: R() < 0.6, wrinkles: true }; p.acc = { stick: true }; p.shoe = "#7A5230";
  } else if (roll < 0.56) {
    p.top = "kurta"; p.topC = pick(["#FFFFFF", "#8DB3D9", "#E9B949"]); p.sleeve = 0.82; p.kurtaLen = 34;
    p.legC = "#FFFFFF"; p.head = "dastar"; p.headC = pick(["#1F4E79", "#E8833A", "#C2477A", "#FFFFFF", "#E9B949"]);
    p.face = { beard: true }; p.hair = "none";
  } else if (roll < 0.74) {
    p.f = true; p.hf = 0.93; p.top = "saree";
    const sc = pick(["#E8833A", "#C2477A", "#2E7D4F", "#1F4E79", "#D94F3D", "#E9B949", "#6C4E9B", "#3E8E8A"]);
    p.topC = sc; p.border = pick(["#E9B949", "#D94F3D", "#FFFFFF", "#1F4E79"]); if (p.border === sc) p.border = "#FFFFFF";
    p.sleeve = 0.24; p.blouse = pick(["#E9B949", "#9E3B2F", "#1F4E79", sc]);
    p.legs = "none"; p.lower = { type: "saree", c: sc, d: 80, pad: 7, border: p.border };
    p.hair = "bun"; p.head = R() < 0.4 ? "ghoonghat" : null;
    p.face = { bindi: true, nath: R() < 0.3, earring: true, sindoor: R() < 0.6 };
    p.acc = { matka: R() < 0.2, jhola: R() < 0.12 }; p.shoe = "#7A5230";
  } else if (roll < 0.85) {
    p.f = true; p.hf = 0.93; p.top = "kurta"; p.topC = pick(["#C2477A", "#2E7D4F", "#8DB3D9", "#E9B949", "#6C4E9B", "#E8833A"]); p.sleeve = 0.6; p.kurtaLen = 40;
    p.legC = pick(["#FFFFFF", "#F3EBDD", "#E9B949"]); p.legW = 15; p.dupatta = pick(["#E9B949", "#FFFFFF", "#D94F3D", "#1F4E79"]);
    if (p.dupatta === p.topC) p.dupatta = "#FFFFFF";
    p.hair = pick(["braid", "bun"] as const); p.face = { bindi: R() < 0.6, earring: true }; p.acc = { jhola: R() < 0.3 };
  } else if (roll < 0.93) {
    p.f = true; p.hf = 0.93; p.top = "tshirt"; p.topC = pick(BRIGHT.concat(LIGHT)); p.name = pick(NF);
    p.legC = pick(["#3E5C84", "#2B3446"]); p.hair = pick(["braid", "pony"] as const);
    p.face = { bindi: R() < 0.3, earring: true, glasses: R() < 0.2 }; p.acc = { phone: R() < 0.4 };
  } else {
    const girl = R() < 0.5;
    p.kid = true; p.f = girl; p.hf = 0.68; p.top = "tshirt"; p.topC = pick(["#FFFFFF", "#8DB3D9", "#E9B949", "#E8833A"]); p.name = pick(NK);
    p.legC = "#1F4E79"; p.legW = 12; p.hair = girl ? "plaits" : "short"; p.acc = { bag: true };
  }
  return p;
}

export type CrowdOptions = { density?: number; speed?: number; bubbles?: boolean; reduced?: boolean };

/** Starts the crowd on a canvas; returns controls. The canvas sizes itself to its CSS box. */
export function startCrowd(cv: HTMLCanvasElement, opts: CrowdOptions = {}) {
  const ctx = cv.getContext("2d");
  if (!ctx) return { setVisible: (_v: boolean) => undefined, destroy: () => undefined };
  const c = ctx;
  const density = opts.density ?? 1, speed = opts.speed ?? 1, bubbles = opts.bubbles ?? true, reduced = !!opts.reduced;

  const tube = (x1: number, y1: number, x2: number, y2: number, w: number, fill: string, ol: number) => {
    c.beginPath(); c.moveTo(x1, y1); c.lineTo(x2, y2);
    c.strokeStyle = INK; c.lineWidth = w + ol * 2; c.stroke();
    c.strokeStyle = fill; c.lineWidth = w; c.stroke();
  };
  const blob = (x: number, y: number, rx: number, ry: number, fill: string, L: number, rot = 0) => {
    c.beginPath(); c.ellipse(x, y, rx, ry, rot, 0, Math.PI * 2);
    c.fillStyle = fill; c.fill(); c.lineWidth = L; c.strokeStyle = INK; c.stroke();
  };
  const dot = (x: number, y: number, r: number, col: string) => { c.beginPath(); c.arc(x, y, r, 0, Math.PI * 2); c.fillStyle = col; c.fill(); };

  const drawPerson = (q: Walker, H: number) => {
    const p = q.p;
    const s = (H / 300) * (0.84 + 0.36 * q.z) * p.hf;
    const gy = H * 0.8 + q.z * H * 0.3;
    const dir = q.dir;
    const sw = Math.sin(q.ph);
    const legA = sw * 0.36, armA = sw * 0.3;
    const LEG = 86, lift = LEG * (1 - Math.cos(legA));
    const L = 1.6 / s;
    const SW = p.f ? 18 : 21, WW = p.f ? 15 : 16.5;
    const hipY = -86, shY = -138, waistY = -84, hy = -164;
    c.save();
    c.translate(q.x, gy);
    c.scale(s * dir, s);
    c.translate(0, lift);
    c.lineJoin = "round"; c.lineCap = "round"; c.lineWidth = L; c.strokeStyle = INK;
    const legs = [{ hx: -6.5, a: legA, fx: 0, fy: 0 }, { hx: 6.5, a: -legA, fx: 0, fy: 0 }];
    legs.forEach((l) => { l.fx = l.hx - LEG * Math.sin(l.a); l.fy = hipY + LEG * Math.cos(l.a); });
    const ground = -lift;

    // back layer
    if (p.acc.bag) {
      c.beginPath(); c.rect(-SW + 1, -146, 2 * SW - 2, 50); c.fillStyle = "#C2477A"; c.fill(); c.lineWidth = L; c.stroke();
    }
    if (p.dupatta) { tube(-SW + 1, shY + 2, -SW - 4, -64, 7, p.dupatta, L); tube(SW - 1, shY + 2, SW + 4, -64, 7, p.dupatta, L); }
    if (p.head === "ghoonghat") {
      c.beginPath(); c.moveTo(-20, -130); c.quadraticCurveTo(-24, -188, 0, -188); c.quadraticCurveTo(24, -188, 20, -130); c.closePath();
      c.fillStyle = p.topC; c.fill(); c.lineWidth = L; c.strokeStyle = INK; c.stroke();
    } else if (p.hair === "bun" || p.hair === "braid" || p.hair === "pony" || p.hair === "plaits") {
      if (p.hair === "bun") blob(0, hy - 18, 6.8, 6.2, p.hairC, L);
      if (p.hair === "pony") blob(12, hy + 4, 5, 13, p.hairC, L, -0.25);
      blob(0, hy + 2, 15.5, 18, p.hairC, L);
    }

    // legs, feet
    if (p.legs !== "none") {
      const lc = p.legs === "skin" ? p.skin : p.legC;
      const lw = p.legW || (p.legs === "skin" ? 9 : 12.5);
      legs.forEach((l) => tube(l.hx, hipY, l.fx, l.fy - 3, lw, lc, L));
    }
    legs.forEach((l) => blob(l.fx + 3.5, l.fy - 2.8, 7, 3.1, p.shoe, L));

    // saree / lungi / dhoti
    if (p.lower) {
      const lo = p.lower, d = lo.d, hemY = hipY + d;
      const xs = legs.map((l) => l.hx - d * Math.sin(l.a) * 0.92);
      const hl = Math.min(xs[0], xs[1]) - lo.pad - 4, hr = Math.max(xs[0], xs[1]) + lo.pad + 4;
      const sk = new Path2D();
      sk.moveTo(-WW - 1, hipY - 4); sk.quadraticCurveTo(-WW - 3, hipY + d * 0.5, hl, hemY);
      sk.lineTo(hr, hemY); sk.quadraticCurveTo(WW + 3, hipY + d * 0.5, WW + 1, hipY - 4); sk.closePath();
      c.fillStyle = lo.c; c.fill(sk);
      c.save(); c.clip(sk); c.lineWidth = L * 0.8;
      const mx = (xs[0] + xs[1]) / 2;
      if (lo.type === "lungi") {
        c.strokeStyle = "rgba(255,255,255,0.4)"; c.beginPath();
        for (let x = -44; x <= 44; x += 7) { c.moveTo(x, hipY - 6); c.lineTo(x, hemY + 2); }
        for (let y = hipY - 4; y <= hemY; y += 7) { c.moveTo(-60, y); c.lineTo(60, y); }
        c.stroke();
      } else if (lo.type === "saree") {
        c.strokeStyle = "rgba(22,24,29,0.32)"; c.beginPath();
        for (let i = 0; i < 4; i++) { c.moveTo(-3 + i * 3.2, hipY + 8); c.lineTo(-3 + i * 3.6 + mx * 0.6, hemY); }
        c.stroke();
        c.fillStyle = lo.border || "#E9B949"; c.fillRect(-70, hemY - 6, 140, 6);
        c.strokeStyle = INK; c.beginPath(); c.moveTo(-70, hemY - 6); c.lineTo(70, hemY - 6); c.stroke();
      } else {
        c.strokeStyle = "rgba(22,24,29,0.28)"; c.beginPath();
        c.moveTo(0, hipY); c.quadraticCurveTo(mx * 0.5, hipY + d * 0.5, mx, hemY);
        c.moveTo(-8, hipY + 6); c.quadraticCurveTo(-2, hipY + 20, 6, hipY + 30);
        c.stroke();
      }
      c.restore();
      c.lineWidth = L; c.strokeStyle = INK; c.stroke(sk);
    }

    tube(0, -153, 0, -139, 8.5, p.skin, L); // neck

    // torso garment
    const tp = new Path2D();
    tp.moveTo(-SW, shY); tp.quadraticCurveTo(-SW - 1.5, -112, -WW, waistY);
    if (p.kurtaLen) {
      const kl = p.kurtaLen, hemY = waistY + kl;
      const xs = legs.map((l) => l.hx - (hemY - hipY) * Math.sin(l.a));
      const hl = Math.min(-WW - 3, Math.min(xs[0], xs[1]) - 9), hr = Math.max(WW + 3, Math.max(xs[0], xs[1]) + 9);
      tp.quadraticCurveTo(-WW - 2, waistY + kl * 0.5, hl, hemY); tp.lineTo(hr, hemY); tp.quadraticCurveTo(WW + 2, waistY + kl * 0.5, WW, waistY);
    } else tp.lineTo(WW, waistY);
    tp.quadraticCurveTo(SW + 1.5, -112, SW, shY); tp.quadraticCurveTo(0, shY - 5, -SW, shY); tp.closePath();
    c.fillStyle = p.topC; c.fill(tp); c.lineWidth = L; c.strokeStyle = INK; c.stroke(tp);

    if (p.top === "tshirt" || p.top === "vest" || p.top === "saree") {
      const deep = p.top === "vest" ? 9 : p.top === "saree" ? 7 : 5;
      c.beginPath(); c.ellipse(0, shY - 2.5, p.top === "vest" ? 8 : 6, deep, 0, 0, Math.PI); c.fillStyle = p.skin; c.fill(); c.stroke();
    }
    if (p.top === "kurta") {
      c.beginPath(); c.moveTo(-5, shY - 4); c.lineTo(-5, shY + 1); c.lineTo(5, shY + 1); c.lineTo(5, shY - 4); c.fillStyle = p.topC; c.fill(); c.stroke();
      c.beginPath(); c.moveTo(0, shY + 1); c.lineTo(0, shY + 22); c.stroke();
      dot(0, shY + 7, 0.9, INK); dot(0, shY + 13, 0.9, INK); dot(0, shY + 19, 0.9, INK);
    }
    if (p.top === "shirt") {
      c.beginPath(); c.moveTo(-6, shY - 3); c.lineTo(0, shY + 7); c.lineTo(6, shY - 3); c.closePath(); c.fillStyle = p.skin; c.fill(); c.stroke();
      c.beginPath(); c.moveTo(-6, shY - 3); c.lineTo(-2, shY + 3); c.moveTo(6, shY - 3); c.lineTo(2, shY + 3); c.moveTo(0, shY + 7); c.lineTo(0, waistY); c.stroke();
      c.strokeRect(-14, shY + 12, 8, 9);
    }
    if (p.top === "saree") {
      const band = new Path2D();
      band.moveTo(-SW + 1, shY - 1); band.lineTo(-SW + 12, shY - 3); band.lineTo(WW + 1, waistY - 3); band.lineTo(WW - 10, waistY + 4); band.closePath();
      c.fillStyle = p.border; c.fill(band); c.stroke(band);
    }
    if (p.name) {
      c.save(); c.scale(dir, 1); // keep the name readable whichever way they walk
      c.fillStyle = textOn(p.topC);
      let fs = 10;
      const font = (n: number) => `700 ${n.toFixed(2)}px "Inter Tight", Inter, "Noto Sans Devanagari", sans-serif`;
      c.font = font(fs);
      const maxW = 2 * WW - (p.acc.bag ? 12 : 0);
      const mw = c.measureText(p.name).width;
      if (mw > maxW) { fs = fs * maxW / mw; c.font = font(fs); }
      c.textAlign = "center"; c.textBaseline = "middle"; c.fillText(p.name, 0, -113);
      c.restore();
    }
    if (p.dupatta) {
      c.beginPath(); c.moveTo(-SW + 2, shY - 1); c.quadraticCurveTo(0, shY + 32, SW - 2, shY - 1);
      c.strokeStyle = INK; c.lineWidth = 8 + 2 * L; c.stroke(); c.strokeStyle = p.dupatta; c.lineWidth = 8; c.stroke();
      c.strokeStyle = INK; c.lineWidth = L;
    }
    if (p.acc.gamchha) {
      tube(-SW + 6, shY - 2, -SW + 4, -102, 7, "#C8372D", L);
      c.save(); c.setLineDash([2.2, 2.2]); c.strokeStyle = "#FFFFFF"; c.lineWidth = 1.6;
      c.beginPath(); c.moveTo(-SW + 6, shY); c.lineTo(-SW + 4, -103); c.stroke(); c.restore();
    }
    if (p.acc.jhola) {
      tube(-SW + 4, shY, WW + 5, -94, 2.6, "#C9A66B", L);
      c.beginPath(); c.rect(WW - 1, -100, 17, 21); c.fillStyle = "#EFE3C8"; c.fill(); c.lineWidth = L; c.strokeStyle = INK; c.stroke();
      c.beginPath(); c.moveTo(WW - 1, -92); c.lineTo(WW + 16, -92); c.strokeStyle = "#C8372D"; c.lineWidth = 2; c.stroke();
      c.strokeStyle = INK; c.lineWidth = L;
    }
    if (p.acc.bag) { tube(-SW + 5, shY + 1, -SW + 6, -100, 2.6, INK, L * 0.3); tube(SW - 5, shY + 1, SW - 6, -100, 2.6, INK, L * 0.3); }

    // arms
    const ARM = p.kid ? 54 : 58;
    const shX = SW - 2.5, shYY = shY + 3;
    const sleeveC = p.top === "saree" ? p.blouse : p.topC;
    const drawArm = (sx: number, a: number): [number, number] => {
      const ex = sx - ARM * Math.sin(a), ey = shYY + ARM * Math.cos(a);
      tube(sx, shYY, ex, ey, p.kid ? 6.5 : 7.5, p.skin, L);
      if (p.sleeve > 0) tube(sx, shYY, sx - ARM * p.sleeve * Math.sin(a), shYY + ARM * p.sleeve * Math.cos(a), 10.5, sleeveC, L);
      blob(ex, ey, p.kid ? 3.6 : 4.2, p.kid ? 3.6 : 4.2, p.skin, L);
      return [ex, ey];
    };
    let rightA = armA - 0.07;
    const leftA = -armA + 0.07;
    if (p.acc.stick) {
      rightA = -0.12;
      const ex = shX - ARM * Math.sin(rightA), ey = shYY + ARM * Math.cos(rightA);
      tube(ex + 1, ey - 8, ex + 4, ground, 3, "#7A5230", L);
    }
    if (p.acc.phone) rightA = -0.38 + armA * 0.15;
    if (!p.acc.matka) drawArm(-shX, leftA);
    const rh = drawArm(shX, rightA);
    if (p.acc.phone) { c.beginPath(); c.rect(rh[0] - 2.5, rh[1] - 8, 5, 9); c.fillStyle = "#2B3446"; c.fill(); c.lineWidth = L; c.strokeStyle = INK; c.stroke(); }

    // head
    c.lineWidth = L; c.strokeStyle = INK;
    blob(-12.6, hy + 1, 3.1, 3.4, p.skin, L); blob(12.6, hy + 1, 3.1, 3.4, p.skin, L); blob(0, hy, 12.6, 14.6, p.skin, L);
    const fc = p.face;
    dot(-4.6, hy - 0.5, 1.3, INK); dot(4.6, hy - 0.5, 1.3, INK);
    c.lineWidth = L * 0.9; c.strokeStyle = INK;
    if (!p.kid) { c.beginPath(); c.moveTo(-7, hy - 5); c.lineTo(-2.6, hy - 5.7); c.moveTo(2.6, hy - 5.7); c.lineTo(7, hy - 5); c.stroke(); }
    c.beginPath(); c.moveTo(0.6, hy + 0.5); c.quadraticCurveTo(2.8, hy + 5.2, 0, hy + 5.6); c.stroke();
    if (fc.beard) {
      c.beginPath(); c.moveTo(-12.4, hy + 1); c.quadraticCurveTo(-12.6, hy + 17, 0, hy + 19); c.quadraticCurveTo(12.6, hy + 17, 12.4, hy + 1);
      c.quadraticCurveTo(9, hy + 8, 4, hy + 7.4); c.quadraticCurveTo(0, hy + 5.6, -4, hy + 7.4); c.quadraticCurveTo(-9, hy + 8, -12.4, hy + 1);
      c.fillStyle = p.hairC; c.fill(); c.lineWidth = L; c.stroke();
      c.beginPath(); c.moveTo(-2.4, hy + 10.5); c.lineTo(2.4, hy + 10.5); c.strokeStyle = "#E9D7C3"; c.stroke(); c.strokeStyle = INK;
    } else {
      if (fc.stache) {
        c.beginPath(); c.moveTo(-7, hy + 9); c.quadraticCurveTo(-3.5, hy + 5.6, 0, hy + 7); c.quadraticCurveTo(3.5, hy + 5.6, 7, hy + 9);
        c.quadraticCurveTo(3, hy + 8.2, 0, hy + 9); c.quadraticCurveTo(-3, hy + 8.2, -7, hy + 9);
        c.fillStyle = fc.stacheC || INK; c.fill(); c.lineWidth = L * 0.8; c.stroke();
      }
      c.beginPath(); c.arc(0, hy + (fc.stache ? 9.6 : 8.4), 2.8, 0.22 * Math.PI, 0.78 * Math.PI); c.lineWidth = L * 0.9; c.stroke();
    }
    if (fc.wrinkles) { c.lineWidth = L * 0.6; c.beginPath(); c.moveTo(-5, hy - 9.5); c.quadraticCurveTo(0, hy - 10.5, 5, hy - 9.5); c.stroke(); }
    if (fc.glasses) {
      c.lineWidth = L * 0.9; c.beginPath(); c.arc(-4.8, hy - 0.5, 3.9, 0, Math.PI * 2); c.moveTo(8.7, hy - 0.5); c.arc(4.8, hy - 0.5, 3.9, 0, Math.PI * 2);
      c.moveTo(-0.9, hy - 0.8); c.lineTo(0.9, hy - 0.8); c.stroke();
    }
    if (fc.bindi) dot(0, hy - 7.6, 1.5, "#C8372D");
    if (fc.tilak) { c.beginPath(); c.moveTo(0, hy - 12); c.lineTo(0, hy - 7); c.strokeStyle = "#E8833A"; c.lineWidth = 1.8; c.stroke(); c.strokeStyle = INK; }
    if (fc.earring) { dot(-12.8, hy + 5.4, 1.4, "#E9B949"); dot(12.8, hy + 5.4, 1.4, "#E9B949"); }
    if (fc.nath) { c.beginPath(); c.arc(2.8, hy + 6, 2.2, 0, Math.PI * 2); c.strokeStyle = "#E9B949"; c.lineWidth = 1; c.stroke(); c.strokeStyle = INK; }
    c.lineWidth = L; c.strokeStyle = INK;

    // hair top + headwear
    if (p.head !== "ghoonghat" && p.head !== "dastar" && p.head !== "pagdi") {
      if (p.hair === "short" || p.hair === "grey") {
        c.beginPath(); c.moveTo(-13.4, hy - 2); c.bezierCurveTo(-14.5, hy - 22, 14.5, hy - 22, 13.4, hy - 2);
        c.quadraticCurveTo(12, hy - 10, 4, hy - 10.5); c.quadraticCurveTo(-6, hy - 11, -13.4, hy - 2);
        c.fillStyle = p.hair === "grey" ? "#BDB6AA" : p.hairC; c.fill(); c.stroke();
      } else if (p.hair === "bald") {
        blob(-12.2, hy - 4, 3.4, 5, "#D8D2C6", L); blob(12.2, hy - 4, 3.4, 5, "#D8D2C6", L);
      } else if (p.hair !== "none") {
        c.beginPath(); c.moveTo(-13.6, hy + 2); c.bezierCurveTo(-15, hy - 22, 15, hy - 22, 13.6, hy + 2);
        c.quadraticCurveTo(10, hy - 8, 0, hy - 12); c.quadraticCurveTo(-10, hy - 8, -13.6, hy + 2);
        c.fillStyle = p.hairC; c.fill(); c.stroke();
        if (fc.sindoor) { c.beginPath(); c.moveTo(0, hy - 16.5); c.lineTo(0, hy - 12.5); c.strokeStyle = "#C8372D"; c.lineWidth = 1.6; c.stroke(); c.strokeStyle = INK; c.lineWidth = L; }
      }
    }
    if (p.head === "topi") {
      c.beginPath(); c.moveTo(-13.5, hy - 9); c.lineTo(-11.5, hy - 21); c.quadraticCurveTo(0, hy - 24, 12, hy - 22); c.lineTo(13.8, hy - 10);
      c.quadraticCurveTo(0, hy - 13, -13.5, hy - 9); c.closePath(); c.fillStyle = "#FFFFFF"; c.fill(); c.stroke();
      c.beginPath(); c.moveTo(-10.5, hy - 19); c.quadraticCurveTo(0, hy - 21.5, 11, hy - 20); c.lineWidth = L * 0.7; c.stroke(); c.lineWidth = L;
    } else if (p.head === "pagdi") {
      c.beginPath(); c.moveTo(-15.5, hy - 3); c.bezierCurveTo(-20, hy - 31, 20, hy - 31, 15.5, hy - 3); c.quadraticCurveTo(0, hy - 10, -15.5, hy - 3); c.closePath();
      c.fillStyle = p.headC; c.fill(); c.stroke();
      c.lineWidth = L * 0.8; c.beginPath(); c.moveTo(-14.5, hy - 9); c.quadraticCurveTo(0, hy - 20, 14, hy - 17);
      c.moveTo(-12.5, hy - 16); c.quadraticCurveTo(2, hy - 26, 12, hy - 22); c.stroke(); c.lineWidth = L;
      if (p.headC === "#D94F3D" || p.headC === "#E8833A" || p.headC === "#C2477A") for (let i = 0; i < 7; i++) dot(-10 + i * 3.4, hy - 12 - (i % 2) * 5, 0.8, "#FFFFFF");
    } else if (p.head === "dastar") {
      c.beginPath(); c.moveTo(-14.6, hy - 4); c.bezierCurveTo(-17.5, hy - 35, 17.5, hy - 35, 14.6, hy - 4); c.lineTo(0, hy - 11); c.closePath();
      c.fillStyle = p.headC; c.fill(); c.stroke();
      c.lineWidth = L * 0.75; c.beginPath(); c.moveTo(-13, hy - 9.5); c.lineTo(0, hy - 23); c.lineTo(13, hy - 9.5);
      c.moveTo(-11.5, hy - 16); c.lineTo(0, hy - 28); c.lineTo(11.5, hy - 16); c.stroke(); c.lineWidth = L;
    } else if (p.head === "ghoonghat") {
      c.beginPath(); c.moveTo(-15, hy + 4); c.bezierCurveTo(-17, hy - 25, 17, hy - 25, 15, hy + 4);
      c.quadraticCurveTo(13, hy - 9, 0, hy - 11.5); c.quadraticCurveTo(-13, hy - 9, -15, hy + 4); c.closePath();
      c.fillStyle = p.topC; c.fill(); c.stroke();
      c.beginPath(); c.moveTo(-14.4, hy + 2); c.quadraticCurveTo(-13, hy - 8.6, 0, hy - 10.6); c.quadraticCurveTo(13, hy - 8.6, 14.4, hy + 2);
      c.strokeStyle = p.border; c.lineWidth = 2; c.stroke(); c.strokeStyle = INK; c.lineWidth = L;
    }
    if (p.hair === "braid" && p.head !== "ghoonghat") {
      for (let i = 0; i < 6; i++) blob(10.5 + i * 0.8, hy + 12 + i * 7, 3.5, 4.4, p.hairC, L, 0.15);
      dot(15.5, hy + 54, 2.4, "#C8372D");
    }
    if (p.hair === "plaits") {
      for (let i = 0; i < 3; i++) { blob(-12 - i * 0.6, hy + 8 + i * 6, 3, 3.6, p.hairC, L); blob(12 + i * 0.6, hy + 8 + i * 6, 3, 3.6, p.hairC, L); }
      blob(-13.6, hy + 27, 3.4, 2.4, "#C8372D", L); blob(13.6, hy + 27, 3.4, 2.4, "#C8372D", L);
    }
    if (p.acc.matka) {
      const my = hy - 30;
      blob(0, hy - 17, 8, 2.6, "#E9B949", L);
      c.beginPath(); c.rect(-5, my - 14, 10, 5); c.fillStyle = "#B5562B"; c.fill(); c.stroke();
      blob(0, my, 12, 10.5, "#B5562B", L); blob(0, my - 14, 6.8, 2.1, "#B5562B", L);
      c.beginPath(); c.ellipse(0, my + 1, 11.6, 3, 0, 0, Math.PI); c.strokeStyle = "#F3EBDD"; c.lineWidth = 1; c.stroke(); c.strokeStyle = INK; c.lineWidth = L;
      // raised, bent arm steadying the pot
      const ex = -27, ey = -158, hx2 = -12.5, hy2 = -191;
      tube(-shX, shYY, ex, ey, 7.5, p.skin, L); tube(ex, ey, hx2, hy2, 7, p.skin, L);
      tube(-shX, shYY, -shX + (ex + shX) * 0.3, shYY + (ey - shYY) * 0.3, 10.5, sleeveC, L);
      blob(hx2, hy2, 4.2, 4.2, p.skin, L);
    }
    c.restore();
    return { x: q.x, y: gy - (p.acc.matka ? 228 : 198) * s };
  };

  const st = { W: 0, H: 0, dpr: 1, crowd: [] as Walker[], bubbles: [] as Bubble[], nextBubble: 900, visible: true, last: 0, raf: 0 };
  const spawn = (anywhere: boolean): Walker => {
    const dir: 1 | -1 = R() < 0.5 ? 1 : -1;
    return { p: make(), z: R(), dir, sp: 0.75 + R() * 0.5, ph: R() * Math.PI * 2, x: anywhere ? R() * st.W : dir > 0 ? -60 : st.W + 60 };
  };
  const populate = () => {
    const n = Math.max(6, Math.min(80, Math.round((st.W / 27) * density)));
    while (st.crowd.length < n) st.crowd.push(spawn(true));
    if (st.crowd.length > n) st.crowd.length = n;
    st.crowd.sort((a, b) => a.z - b.z);
  };
  const roundBox = (x: number, y: number, w: number, h: number, r: number) => {
    c.beginPath(); c.moveTo(x + r, y); c.lineTo(x + w - r, y); c.quadraticCurveTo(x + w, y, x + w, y + r);
    c.lineTo(x + w, y + h - r); c.quadraticCurveTo(x + w, y + h, x + w - r, y + h); c.lineTo(x + r, y + h);
    c.quadraticCurveTo(x, y + h, x, y + h - r); c.lineTo(x, y + r); c.quadraticCurveTo(x, y, x + r, y); c.closePath();
  };
  const drawBubble = (b: Bubble, head: { x: number; y: number }, now: number) => {
    const age = now - b.t0;
    const a = Math.min(1, age / 220, (b.life - age) / 260);
    if (a <= 0) return;
    c.save(); c.globalAlpha = a; c.font = `500 13px ${FAM}`;
    const w = c.measureText(b.text).width + 22, h = 30;
    const bx = Math.max(6, Math.min(st.W - w - 6, head.x - w / 2));
    const by = Math.max(4, head.y - h - 12 - (1 - a) * 6);
    roundBox(bx, by, w, h, 12); c.fillStyle = "#FFFFFF"; c.fill(); c.lineWidth = 1.3; c.strokeStyle = INK; c.stroke();
    const tx = Math.max(bx + 14, Math.min(bx + w - 14, head.x));
    c.beginPath(); c.moveTo(tx - 5, by + h - 0.5); c.lineTo(tx, by + h + 7); c.lineTo(tx + 5, by + h - 0.5); c.fillStyle = "#FFFFFF"; c.fill(); c.stroke();
    c.fillStyle = INK; c.textAlign = "center"; c.textBaseline = "middle"; c.fillText(b.text, bx + w / 2, by + h / 2 + 0.5);
    c.restore();
  };
  const frame = (now: number, dt: number) => {
    const { W, H } = st;
    c.setTransform(st.dpr, 0, 0, st.dpr, 0, 0);
    c.clearRect(0, 0, W, H);
    let resort = false;
    for (let i = 0; i < st.crowd.length; i++) {
      const q = st.crowd[i];
      const s = (H / 300) * (0.84 + 0.36 * q.z) * q.p.hf;
      q.x += q.dir * q.sp * 0.058 * s * dt * speed;
      q.ph += q.sp * 0.0056 * dt * speed;
      if ((q.dir > 0 && q.x > W + 70) || (q.dir < 0 && q.x < -70)) {
        st.bubbles = st.bubbles.filter((b) => b.q !== q);
        st.crowd[i] = spawn(false); resort = true;
      }
    }
    if (resort) st.crowd.sort((a, b) => a.z - b.z);
    const heads = new Map<Walker, { x: number; y: number }>();
    for (const q of st.crowd) heads.set(q, drawPerson(q, H));
    if (bubbles && !reduced) {
      st.nextBubble -= dt;
      if (st.nextBubble <= 0 && st.bubbles.length < 2) {
        const cands = st.crowd.filter((q) => q.x > 90 && q.x < W - 90 && !st.bubbles.some((b) => b.q === q));
        if (cands.length) st.bubbles.push({ q: pick(cands), text: pick(SAY), t0: now, life: 2900 });
        st.nextBubble = 1500 + R() * 1400;
      }
      st.bubbles = st.bubbles.filter((b) => now - b.t0 < b.life);
      for (const b of st.bubbles) { const h = heads.get(b.q); if (h) drawBubble(b, h, now); }
    }
  };
  const resize = () => {
    const W = cv.clientWidth, H = cv.clientHeight;
    if (!W || !H) return;
    st.dpr = Math.min(window.devicePixelRatio || 1, W < 700 ? 1.5 : 2);
    cv.width = Math.round(W * st.dpr); cv.height = Math.round(H * st.dpr);
    st.W = W; st.H = H;
    populate();
    frame(performance.now(), 0);
  };
  const ro = typeof ResizeObserver !== "undefined" ? new ResizeObserver(resize) : null;
  ro?.observe(cv);
  resize();
  if (!reduced) {
    st.last = performance.now();
    const loop = (now: number) => {
      const dt = Math.min(48, now - st.last);
      st.last = now;
      if (st.visible && st.W) frame(now, dt);
      st.raf = requestAnimationFrame(loop);
    };
    st.raf = requestAnimationFrame(loop);
  }
  return {
    setVisible: (v: boolean) => { st.visible = v; st.last = performance.now(); },
    destroy: () => { cancelAnimationFrame(st.raf); ro?.disconnect(); },
  };
}
