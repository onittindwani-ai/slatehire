import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const css = readFileSync(join(__dirname, "../src/styles/tokens.css"), "utf8");

function block(selector: string): string {
  const i = css.indexOf(selector + " {");
  if (i < 0) throw new Error(`missing ${selector}`);
  return css.slice(i, css.indexOf("}", i));
}
function vars(b: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const m of b.matchAll(/--(sx-[\w-]+):\s*(#[0-9a-fA-F]{6})/g)) out[m[1]!] = m[2]!;
  return out;
}
function lum(hex: string): number {
  const c = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return 0.2126 * c[0]! + 0.7152 * c[1]! + 0.0722 * c[2]!;
}
export function contrast(a: string, b: string): number {
  const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p);
  return (x! + 0.05) / (y! + 0.05);
}

const light = vars(block(":root"));
const dark = { ...light, ...vars(block('[data-theme="dark"]')) };
const accents = ["clay", "sage", "slate", "plum", "ochre", "teal", "rose"];

describe("WCAG AA contrast of the tokens", () => {
  for (const [name, t] of [["light", light], ["dark", dark]] as const) {
    it(`${name}: body and secondary text on every surface`, () => {
      for (const surface of ["sx-bg", "sx-surface", "sx-surface-2"]) {
        for (const text of ["sx-ink", "sx-ink-2", "sx-ink-3"]) {
          expect(contrast(t[text]!, t[surface]!), `${text} on ${surface}`).toBeGreaterThanOrEqual(4.5);
        }
      }
    });
    it(`${name}: status colours on their backgrounds`, () => {
      for (const s of ["success", "warning", "danger"]) expect(contrast(t[`sx-${s}`]!, t[`sx-${s}-bg`]!), s).toBeGreaterThanOrEqual(4.5);
    });
    it(`${name}: primary button text on the default accent`, () => {
      expect(contrast(t["sx-accent-ink"]!, t["sx-accent"]!)).toBeGreaterThanOrEqual(4.5);
    });
  }
  for (const a of accents) {
    for (const theme of ["light", "dark"] as const) {
      it(`accent ${a} (${theme}): button text and soft chip`, () => {
        const sel = theme === "light" ? `[data-accent="${a}"]` : `[data-theme="dark"][data-accent="${a}"]`;
        const v = vars(block(sel));
        const base = theme === "light" ? light : dark;
        expect(contrast(base["sx-accent-ink"]!, v["sx-accent"]!), "button text").toBeGreaterThanOrEqual(4.5);
        expect(contrast(base["sx-ink"]!, v["sx-accent-soft"]!), "chip text").toBeGreaterThanOrEqual(4.5);
        expect(contrast(base["sx-ink-2"]!, v["sx-accent-soft"]!), "chip secondary text").toBeGreaterThanOrEqual(4.5);
      });
    }
  }
});
