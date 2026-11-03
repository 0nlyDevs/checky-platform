import assert from "node:assert/strict";
import { test } from "node:test";
import { shorterColumn, stickyTop } from "./sticky.ts";

test("a column that fits sticks under the bar", () => {
  assert.equal(stickyTop(84, 900, 400), 100);
});

test("a column taller than the viewport sticks by its bottom", () => {
  assert.equal(stickyTop(84, 900, 1100), -224);
});

test("the bottom margin is adjustable", () => {
  assert.equal(stickyTop(84, 900, 1100, 0), -200);
});

test("the shorter of two columns sticks, whichever side it is on", () => {
  const main = { left: 0, top: 0, bottom: 2400 };
  const side = { left: 900, top: 0, bottom: 600 };
  assert.equal(shorterColumn([main, side]), 1);
  assert.equal(shorterColumn([{ ...main, bottom: 500 }, side]), 0);
});

test("a column of several children is measured from its first top to its last bottom", () => {
  const boxes = [
    { left: 0, top: 0, bottom: 300 },
    { left: 0, top: 340, bottom: 700 },
    { left: 900, top: 0, bottom: 1500 },
  ];
  assert.equal(shorterColumn(boxes), null);
  assert.equal(shorterColumn([...boxes.slice(0, 2), { left: 900, top: 0, bottom: 400 }]), 2);
});

test("nothing sticks on one column, on equal columns or on three columns", () => {
  assert.equal(shorterColumn([{ left: 16, top: 0, bottom: 500 }, { left: 16, top: 540, bottom: 900 }]), null);
  assert.equal(shorterColumn([{ left: 0, top: 0, bottom: 500 }, { left: 900, top: 0, bottom: 500.4 }]), null);
  assert.equal(
    shorterColumn([{ left: 0, top: 0, bottom: 500 }, { left: 400, top: 0, bottom: 200 }, { left: 800, top: 0, bottom: 900 }]),
    null,
  );
});
