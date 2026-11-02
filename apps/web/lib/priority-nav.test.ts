import assert from "node:assert/strict";
import { test } from "node:test";
import { foldTabs } from "./priority-nav.ts";

test("every tab stays in the bar when they all fit", () => {
  assert.deepEqual(foldTabs([100, 100, 100], 400, 80, 1), { visible: 3, activeFolded: false });
});

test("tabs fold from the end and leave room for « Plus »", () => {
  assert.deepEqual(foldTabs([100, 100, 100, 100], 330, 80, 0), { visible: 2, activeFolded: false });
});

test("a folded active tab is reported so « Plus » can carry it", () => {
  assert.deepEqual(foldTabs([100, 100, 100, 100], 330, 80, 3), { visible: 2, activeFolded: true });
});

test("the first tab never folds, even without room", () => {
  assert.deepEqual(foldTabs([300, 300], 100, 80, 1), { visible: 1, activeFolded: true });
});

test("no active tab is never folded", () => {
  assert.deepEqual(foldTabs([100, 100, 100, 100], 330, 80, -1), { visible: 2, activeFolded: false });
});
