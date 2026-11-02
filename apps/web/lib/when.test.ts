import assert from "node:assert/strict";
import { test } from "node:test";
import { exact, plural, relative } from "./when.ts";

const now = new Date("2026-11-02T09:41:00Z");

test("relative reads hours within the same Madagascar day", () => {
  assert.equal(relative("2026-11-02T03:41:00Z", now), "il y a 6 h");
});

test("relative reads the instant and the minutes", () => {
  assert.equal(relative("2026-11-02T09:40:40Z", now), "à l'instant");
  assert.equal(relative("2026-11-02T09:36:00Z", now), "il y a 5 min");
});

test("relative says hier for the previous calendar day in UTC+3", () => {
  // 21:30Z on the 1st is 00:30 on the 2nd in Madagascar: same day as now, not yesterday.
  assert.equal(relative("2026-11-01T21:30:00Z", now), "il y a 12 h");
  assert.equal(relative("2026-11-01T20:30:00Z", now), "hier");
  assert.equal(relative("2026-11-01T05:00:00Z", now), "hier");
});

test("relative falls back to the date, with the year only when it differs", () => {
  assert.equal(relative("2026-10-28T08:00:00Z", now), "28/10");
  assert.equal(relative("2023-03-14T08:00:00Z", now), "14/03/2023");
});

test("relative and exact print a dash for an unreadable date", () => {
  assert.equal(relative("nope", now), "—");
  assert.equal(exact("nope"), "—");
});

test("exact prints the Madagascar wall clock", () => {
  assert.equal(exact("2026-11-01T21:41:00Z"), "02/11/2026 à 00:41");
});

test("plural keeps the singular for 0 and 1", () => {
  assert.equal(plural(0, "source", "sources"), "0 source");
  assert.equal(plural(1, "source", "sources"), "1 source");
  assert.equal(plural(2, "source", "sources"), "2 sources");
});
