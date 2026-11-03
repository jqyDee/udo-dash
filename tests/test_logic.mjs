process.env.TZ = "Europe/Vienna";

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import vm from "node:vm";

const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
const source = html.match(/<script id="logic">([\s\S]*?)<\/script>/)[1];
// Run in this realm so results compare with assert's strict equality.
const L = vm.runInThisContext(`(() => {${source}\nreturn L;})()`);
const eq = assert.deepEqual;
const plain = (value) => JSON.parse(JSON.stringify(value));

const d = (y, m, day) => new Date(y, m - 1, day);
const range = (a, b) => ({ from: a, to: b });
const row = (start, end, extra = {}) => ({
  full_id: "s1",
  task: "lab",
  path: "Uni/CS/lab",
  start,
  end,
  minutes: 0,
  ...extra,
});
const keys = (r) => [L.dayKey(r.from), L.dayKey(r.to)];

test("day helpers", () => {
  eq(L.dayKey(d(2026, 3, 5)), "2026-03-05");
  eq(L.dayKey(L.fromKey("2026-11-02")), "2026-11-02");
  eq(L.dayKey(L.addDays(d(2026, 10, 31), 1)), "2026-11-01");
  eq(L.dayKey(L.mondayOf(d(2026, 11, 1))), "2026-10-26");
  eq(L.dayKey(L.mondayOf(d(2026, 11, 2))), "2026-11-02");
});

test("day helpers cross the clock change", () => {
  eq(L.dayKey(L.addDays(d(2026, 10, 25), 1)), "2026-10-26");
  eq(L.dayKey(L.addDays(d(2026, 3, 29), 1)), "2026-03-30");
});

test("ranges", () => {
  eq(keys(L.weekRange(d(2026, 11, 2))), ["2026-11-02", "2026-11-09"]);
  eq(keys(L.monthRange(d(2026, 10, 1))), ["2026-09-28", "2026-11-02"]);
  eq(keys(L.monthRange(d(2027, 2, 1))), ["2027-02-01", "2027-03-01"]);
  eq(keys(L.monthRange(d(2027, 8, 1))), ["2027-07-26", "2027-09-06"]);
  eq(keys(L.stripRange(d(2026, 11, 3), 7)), ["2026-10-28", "2026-11-04"]);
});

test("pieces split a session across midnight", () => {
  const rows = [row("2026-10-01T23:00:00+02:00", "2026-10-02T01:00:00+02:00")];
  const both = L.pieces(rows, range(d(2026, 10, 1), d(2026, 10, 3)), 0);
  eq(
    both.map((p) => [p.day, p.startMin, p.endMin, p.seconds]),
    [
      ["2026-10-01", 1380, 1440, 3600],
      ["2026-10-02", 0, 60, 3600],
    ],
  );
});

test("pieces clip to the range", () => {
  const rows = [row("2026-10-01T23:00:00+02:00", "2026-10-02T01:00:00+02:00")];
  const second = L.pieces(rows, range(d(2026, 10, 2), d(2026, 10, 3)), 0);
  eq(second.map((p) => [p.day, p.startMin, p.endMin]), [["2026-10-02", 0, 60]]);
  const first = L.pieces(rows, range(d(2026, 10, 1), d(2026, 10, 2)), 0);
  eq(first.map((p) => [p.day, p.startMin, p.endMin]), [["2026-10-01", 1380, 1440]]);
});

test("pieces outside the range disappear", () => {
  const rows = [row("2026-10-05T10:00:00+02:00", "2026-10-05T11:00:00+02:00")];
  eq(L.pieces(rows, range(d(2026, 10, 1), d(2026, 10, 3)), 0), []);
});

test("running session ends now", () => {
  const start = "2026-11-02T10:00:00+01:00";
  const now = Date.parse("2026-11-02T10:30:00+01:00");
  const [p] = L.pieces([row(start, null)], range(d(2026, 11, 2), d(2026, 11, 3)), now);
  eq([p.running, p.seconds, p.endMin], [true, 1800, 630]);
});

test("running session across midnight gives one piece per day", () => {
  const now = Date.parse("2026-11-03T00:30:00+01:00");
  const out = L.pieces(
    [row("2026-11-02T23:30:00+01:00", null)],
    range(d(2026, 11, 2), d(2026, 11, 4)),
    now,
  );
  eq(
    out.map((p) => [p.day, p.startMin, p.endMin, p.running]),
    [
      ["2026-11-02", 1410, 1440, true],
      ["2026-11-03", 0, 30, true],
    ],
  );
});

test("removed task is skipped", () => {
  const rows = [row("2026-11-02T10:00:00+01:00", "2026-11-02T11:00:00+01:00", { path: null })];
  eq(L.pieces(rows, range(d(2026, 11, 2), d(2026, 11, 3)), 0), []);
});

test("sessions land at wall-clock time on the clock change day", () => {
  const rows = [row("2026-10-25T10:00:00+01:00", "2026-10-25T11:00:00+01:00")];
  const [p] = L.pieces(rows, range(d(2026, 10, 25), d(2026, 10, 26)), 0);
  eq([p.day, p.startMin, p.endMin, p.seconds], ["2026-10-25", 600, 660, 3600]);
});

test("fmtSeconds rounds down to minutes", () => {
  eq(L.fmtSeconds(475.56 * 60), "7h55");
  eq(L.fmtSeconds(240), "4m");
  eq(L.fmtSeconds(3600), "1h");
  eq(L.fmtSeconds(0), "0m");
  eq(L.fmtSeconds(59), "0m");
  eq(L.fmtSeconds(3660), "1h01");
});

const lsRows = [
  { path: "Errand", name: "Errand", depth: 0, status: "to do", due: "2026-10-30T12:00:00+01:00", minutes: 0, estimate: null },
  { path: "Solo", name: "Solo", depth: 0, status: "started", minutes: 0, estimate: null },
  { path: "Old", name: "Old", depth: 0, status: "done", due: "2026-01-01T12:00:00+01:00", minutes: 5, estimate: 5 },
  { path: "Uni", name: "Uni", depth: 0, kind: "workspace" },
  { path: "Uni/Loose", name: "Loose", depth: 1, status: "to do", due: "2026-11-20T12:00:00+01:00", minutes: 0, estimate: 30 },
  { path: "Uni/A", name: "A", depth: 1, kind: "project" },
  { path: "Uni/A/Exercise 10", name: "Exercise 10", depth: 2, status: "done", minutes: 0 },
  { path: "Uni/A/Exercise 2", name: "Exercise 2", depth: 2, status: "started", due: "2026-11-09T23:59:00+01:00", minutes: 328, estimate: 327 },
  { path: "Uni/A/Exercise 1", name: "Exercise 1", depth: 2, status: "started", due: "2026-11-04T08:00:00+01:00", minutes: 294, estimate: 373 },
  { path: "Uni/A/Exercise 3", name: "Exercise 3", depth: 2, status: "done", minutes: 0 },
  { path: "Uni/A/Exercise 4", name: "Exercise 4", depth: 2, status: "done", minutes: 0 },
  { path: "Uni/A/Exercise 5", name: "Exercise 5", depth: 2, status: "done", minutes: 0 },
  { path: "Uni/AB", name: "AB", depth: 1, kind: "project" },
  { path: "Uni/AB/Thing", name: "Thing", depth: 2, status: "done", minutes: 0 },
];
const tree = L.buildTree(lsRows);

test("tree relations", () => {
  eq(tree.containerName("Uni/A/Exercise 1"), "A");
  eq(tree.containerName("Uni/Loose"), "Uni");
  eq(tree.containerName("Errand"), null);
  eq(tree.projectOf("Uni/A/Exercise 1"), "Uni/A");
  eq(tree.projectOf("Uni/A"), "Uni/A");
  eq(tree.projectOf("Uni/Loose"), null);
  eq(tree.projectOf("Errand"), null);
  eq(tree.groupOf("Uni/A/Exercise 1"), "Uni/A");
  eq(tree.groupOf("Uni/Loose"), "Uni");
  eq(tree.groupOf("Errand"), null);
  eq(tree.parent("Uni/A/Exercise 1"), "Uni/A");
  eq(tree.parent("Errand"), null);
  eq(tree.children("Uni/A").map((r) => r.name).slice(0, 3), ["Exercise 1", "Exercise 2", "Exercise 3"]);
  eq(tree.children("Uni").map((r) => r.path), ["Uni/A", "Uni/AB", "Uni/Loose"]);
});

test("project colors follow path order, through 8 slots", () => {
  const c = L.colors(tree);
  // Groups: Uni (has a direct task), Uni/A, Uni/AB.
  eq(c.project("Uni"), "--s1");
  eq(c.project("Uni/A"), "--s2");
  eq(c.project("Uni/AB"), "--s3");
  eq(c.project(null), "--neutral");
  const many = Array.from({ length: 9 }, (_, i) => ({
    path: `P${i}`, name: `P${i}`, depth: 0, kind: "project",
  }));
  const big = L.colors(L.buildTree(many));
  eq(big.project("P7"), "--s8");
  eq(big.project("P8"), "--s1");
});

test("task colors follow natural name order and repeat after five", () => {
  const c = L.colors(tree);
  eq(c.task("Uni/A/Exercise 1"), "--t1");
  eq(c.task("Uni/A/Exercise 2"), "--t2");
  eq(c.task("Uni/A/Exercise 5"), "--t5");
  eq(c.task("Uni/A/Exercise 10"), "--t1");
  eq(c.task("Uni/Loose"), "--t1");
  eq(c.task("Errand"), "--t1");
  eq(c.task("Solo"), "--t3");
});

test("colors of unknown paths don't crash", () => {
  const c = L.colors(tree);
  eq(c.project("Nope"), "--neutral");
  eq(c.task("Nope/x"), "--t1");
});

test("matches a task by itself and a project by prefix", () => {
  assert.ok(L.matches("Uni/A/Exercise 1", "Uni/A/Exercise 1"));
  assert.ok(L.matches("Uni/A/Exercise 1", "Uni/A"));
  assert.ok(!L.matches("Uni/AB/Thing", "Uni/A"));
  assert.ok(!L.matches("Uni/A/Exercise 2", "Uni/A/Exercise 1"));
  assert.ok(!L.matches("Uni/A/Exercise 1", null));
});

test("clicking a session moves an active highlight only if the session is grayed out", () => {
  const next = (hl, path) => L.highlightAfterSessionClick(hl, path, tree);
  eq(next(null, "Uni/A/Exercise 1"), null);
  eq(next("Uni/A", "Uni/A/Exercise 1"), "Uni/A");
  eq(next("Uni/A/Exercise 1", "Uni/A/Exercise 1"), "Uni/A/Exercise 1");
  eq(next("Uni/A", "Uni/AB/Thing"), "Uni/AB");
  eq(next("Uni/A/Exercise 1", "Uni/AB/Thing"), "Uni/AB");
  eq(next("Uni/A/Exercise 1", "Uni/A/Exercise 2"), "Uni/A");
  eq(next("Uni/A", "Uni/Loose"), "Uni/Loose");
  eq(next("Uni/A", "Errand"), "Errand");
});

const state = (over = {}) => ({ hl: null, sel: null, day: null, zoom: { v0: 100, span: 200 }, ...over });
const node = (path, session) => (session ? { type: "node", path, session } : { type: "node", path });

test("Esc: task, project, nothing, then zoom in strips", () => {
  const s = state({ hl: "Uni/A/Exercise 1", sel: node("Uni/A/Exercise 1") });
  L.escStep(s, tree, "strips");
  eq([s.hl, s.sel.path, s.zoom.span], ["Uni/A", "Uni/A", 200]);
  L.escStep(s, tree, "strips");
  eq([s.hl, s.sel, s.zoom.span], [null, null, 200]);
  L.escStep(s, tree, "strips");
  eq(plain(s.zoom), { v0: 0, span: 1440 });
});

test("Esc: project highlighted and task in panel shows the project first", () => {
  const s = state({ hl: "Uni/A", sel: node("Uni/A/Exercise 1", { id: "x" }) });
  L.escStep(s, tree, "week");
  eq([s.hl, s.sel.path, s.sel.session], ["Uni/A", "Uni/A", undefined]);
});

test("Esc: highlight goes before an open day, then the day closes", () => {
  const s = state({ hl: "Uni/A", sel: { type: "day", k: "2026-10-30" }, day: "2026-10-30" });
  L.escStep(s, tree, "week");
  eq([s.hl, s.sel.type, s.day], [null, "day", "2026-10-30"]);
  L.escStep(s, tree, "week");
  eq([s.sel, s.day], [null, null]);
});

test("Esc: leaves the zoom alone outside strips", () => {
  const s = state();
  L.escStep(s, tree, "week");
  eq(s.zoom.span, 200);
});

test("Esc: a task with no project goes straight to nothing", () => {
  for (const path of ["Errand", "Uni/Loose"]) {
    const s = state({ hl: path, sel: node(path) });
    L.escStep(s, tree, "week");
    eq([s.hl, s.sel], [null, null]);
  }
});

test("Esc: a panel with no highlight closes", () => {
  const s = state({ sel: node("Uni/A/Exercise 1", { id: "x" }) });
  L.escStep(s, tree, "strips");
  eq([s.sel, s.zoom.span], [null, 200]);
});

test("dueState", () => {
  const due = "2026-11-04T08:00:00+01:00";
  const at = (hoursBefore) => Date.parse(due) - hoursBefore * 3600e3;
  eq(L.dueState(due, at(-1)).kind, "late");
  eq(plain(L.dueState(due, at(21.5))), { kind: "soon", text: "due in 21h" });
  eq(plain(L.dueState(due, at(40 / 60))), { kind: "soon", text: "due in 40m" });
  eq(L.dueState(due, at(25)).kind, "ok");
  eq(L.dueState(due, at(24)).kind, "ok");
  eq(L.dueState(undefined, 0).kind, "none");
});

test("a done task never warns", () => {
  const now = Date.parse("2026-11-03T00:10:00+01:00");
  const due = "2026-10-21T08:00:00+02:00";
  eq(L.taskWarning({ status: "done", due }, now).kind, "none");
  eq(L.taskWarning({ status: "started", due }, now).kind, "late");
  eq(L.taskWarning({ status: "to do" }, now).kind, "none");
});

test("todoItems sorts by due and leaves out done tasks", () => {
  const now = Date.parse("2026-11-03T00:10:00+01:00");
  const items = L.todoItems(tree, now);
  eq(
    items.map((i) => i.row.path),
    ["Errand", "Uni/A/Exercise 1", "Uni/A/Exercise 2", "Uni/Loose", "Solo"],
  );
  eq(
    items.map((i) => i.left),
    ["no estimate", "1h19 left", "1m over", "30m left", "no estimate"],
  );
  eq(
    items.map((i) => i.when),
    ["overdue, 4 days ago", "tomorrow", "in 6 days", "in 17 days", "no due date"],
  );
});

test("statusView", () => {
  const now = Date.parse("2026-11-03T12:30:00+01:00");
  const running = (task, started) => ({ running: { task, started, ended: null, minutes: 0 } });
  eq(L.statusView({ running: null }, tree, now), null);
  eq(
    plain(L.statusView(running("Exercise 1", "2026-11-03T10:15:30+01:00"), tree, now)),
    { task: "Exercise 1", path: "Uni/A/Exercise 1", container: "A", elapsed: "2h14", since: "since 10:15" },
  );
  // Started on an earlier day: the start says which day.
  eq(L.statusView(running("Solo", "2026-11-02T23:00:00+01:00"), tree, now).since, "since 2 Nov 23:00");
  // Unknown or ambiguous name: no path to link to, but still shown.
  const twice = L.buildTree([
    { path: "A", name: "A", depth: 0, kind: "project" },
    { path: "B", name: "B", depth: 0, kind: "project" },
    { path: "A/lab", name: "lab", depth: 1, status: "started" },
    { path: "B/lab", name: "lab", depth: 1, status: "to do" },
  ]);
  const ambiguous = L.statusView(running("lab", "2026-11-03T12:00:00+01:00"), twice, now);
  eq([ambiguous.task, ambiguous.path, ambiguous.container, ambiguous.elapsed], ["lab", null, null, "30m"]);
  eq(L.statusView(running("gone", "2026-11-03T12:00:00+01:00"), tree, now).path, null);
});

test("weekHourHeight fits the space, within its limits", () => {
  eq(L.weekHourHeight(24 * 30), 30);
  eq(L.weekHourHeight(24 * 38.75), 38.75);
  eq(L.weekHourHeight(5000), 38.75);
  eq(L.weekHourHeight(24 * 16), 16);
  eq(L.weekHourHeight(100), 16);
  eq(L.weekHourHeight(-50), 16);
});

test("zoomAt keeps the time under the cursor and clamps", () => {
  let z = { v0: 0, span: 1440 };
  const at = 0.75 * 1440;
  z = L.zoomAt(z, 0.75, -60);
  assert.ok(z.span < 1440);
  assert.ok(Math.abs(z.v0 + 0.75 * z.span - at) < 1e-6);
  for (let i = 0; i < 50; i++) z = L.zoomAt(z, 0.75, -60);
  eq(z.span, 60);
  for (let i = 0; i < 50; i++) z = L.zoomAt(z, 0.75, 60);
  eq(plain(z), { v0: 0, span: 1440 });
});

test("panBy clamps at both ends", () => {
  eq(plain(L.panBy({ v0: 100, span: 200 }, 50)), { v0: 150, span: 200 });
  eq(plain(L.panBy({ v0: 100, span: 200 }, -500)), { v0: 0, span: 200 });
  eq(plain(L.panBy({ v0: 100, span: 200 }, 5000)), { v0: 1240, span: 200 });
});

test("tickList adapts to the span", () => {
  const full = L.tickList(0, 1440);
  eq(full.ticks.map(full.label), ["00", "03", "06", "09", "12", "15", "18", "21", "24"]);
  const close = L.tickList(960, 72);
  eq(close.ticks.map(close.label), ["16:00", "16:15", "16:30", "16:45", "17:00"]);
});
