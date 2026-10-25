import { describe, expect, it } from "vitest";
import html from "../index.html?raw";
import manifestRaw from "../public/manifest.webmanifest?raw";
import sw from "../public/sw.js?raw";

// Vite globs (no Node APIs, so this file typechecks with the app's tsconfig).
const sources = import.meta.glob(["/src/**/*.{ts,tsx,css}", "!/src/brand.test.ts"], { query: "?raw", import: "default", eager: true }) as Record<string, string>;
const publicFiles = Object.keys(import.meta.glob("/public/**/*"));
const exists = (p: string) => publicFiles.includes(`/public${p}`);

describe("brand assets", () => {
  it("no references to the old logo remain", () => {
    expect(Object.keys(sources).length).toBeGreaterThan(10);
    for (const [name, text] of Object.entries({ "index.html": html, "manifest.webmanifest": manifestRaw, "sw.js": sw, ...sources })) {
      expect(text, name).not.toMatch(/["'(]\/icon\.svg/);
    }
    expect(exists("/icon.svg")).toBe(false);
  });

  it("every manifest icon and favicon exists", () => {
    const manifest = JSON.parse(manifestRaw);
    expect(manifest.icons.length).toBeGreaterThan(0);
    for (const icon of manifest.icons) expect(exists(icon.src), icon.src).toBe(true);
    expect(manifest.icons.some((i: { purpose?: string }) => i.purpose === "maskable")).toBe(true);
    for (const m of html.matchAll(/(?:href|content)="(\/brand\/[^"]+)"/g)) expect(exists(m[1]), m[1]).toBe(true);
  });

  it("the logo SVG keeps its viewBox", () => {
    const svg = import.meta.glob("/public/brand/anvaya-mark.svg", { query: "?raw", import: "default", eager: true }) as Record<string, string>;
    expect(Object.values(svg)[0]).toContain('viewBox="0 0 64 64"');
  });
});
