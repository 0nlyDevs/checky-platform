import assert from "node:assert/strict";
import { test } from "node:test";
import { contrast, dark, light, PAIRS } from "./tokens.ts";

test("contrast matches known ratios", () => {
  assert.ok(Math.abs(contrast("#0a0a0b", "#f3f2ee") - 17.67) <= 0.05);
  assert.equal(contrast("#f3f2ee", "#f3f2ee"), 1);
});

for (const [name, theme] of [["light", light], ["dark", dark]] as const) {
  test(`every text/background pair reaches 4.5:1 in ${name}`, () => {
    for (const [fg, bg] of PAIRS) {
      const ratio = contrast(theme[fg], theme[bg]);
      assert.ok(ratio >= 4.5, `${name}: ${fg} (${theme[fg]}) on ${bg} (${theme[bg]}) is ${ratio.toFixed(2)}:1`);
    }
  });
}

test("the active nav pill keeps the fixed ink label in dark", () => {
  assert.equal(dark["nav-active-foreground"], "#0a0a0b");
});
