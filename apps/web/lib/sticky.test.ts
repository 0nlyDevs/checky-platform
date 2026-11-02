import assert from "node:assert/strict";
import { test } from "node:test";
import { stickyTop } from "./sticky.ts";

test("a column that fits sticks under the bar", () => {
  assert.equal(stickyTop(84, 900, 400), 100);
});

test("a column taller than the viewport sticks by its bottom", () => {
  assert.equal(stickyTop(84, 900, 1100), -224);
});

test("the bottom margin is adjustable", () => {
  assert.equal(stickyTop(84, 900, 1100, 0), -200);
});
