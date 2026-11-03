# udo-dash: design

A small local browser dashboard for udo time tracking. Personal tool, separate
from the udo project. It uses the `udo` CLI as its only data source.

The agreed look and behaviour is in the clickable prototype,
`docs/prototype/prototype-v5.html`. Open it directly in a browser. Where this
document and the prototype disagree, this document wins. The prototype has pasted
data and stand-ins that the real build replaces (see "Prototype differences").

## Why

1. See when work happened, per day, week and month.
2. Find out what the TUI stats view should show later (udo issue #84). Cheap
   experiments here are the input for that. Anything awkward to get out of udo's
   JSON is a finding worth keeping.
3. See at a glance what is due and when.

## Goals

- Three switchable calendar views (week, month, day strips) of real udo sessions.
- A To do section with open tasks, due dates and warnings.
- A side panel with details for whatever was clicked.
- Highlighting by project or task that works in all views.
- Loads only the data the current view needs.

## Non-goals

- Editing anything. No starting timers, correcting sessions or changing tasks.
- Multiple users, remote access, accounts, deployment.
- Charts beyond the three views for now. New ones can be tried later.
- Replacing `udo stats` or the TUI.

## Anti-goals: a failure even if it works

- Writing to udo data, or running any udo command that can.
- Reading `udo.db` or `.udo.toml` directly. The CLI's JSON is the only interface.
- Requiring changes in the udo repo for the dashboard to work.
- A dependency install or build step before it runs.
- Sending data anywhere: no CDN, fonts, analytics or other network requests. It
  must work offline.

## Constraints

- Separate repo at `~/Developer/projects/udo-dash`.
- Commits in this repo use sign-off (`git commit -s`).
- Runs on the owner's Mac against udo 0.5.0 from `PATH`, honouring `UDO_ROOT`.

## How it is built

- **Server:** one Python file, `udo_dash.py`, standard library only
  (`http.server`, `subprocess`, `json`). Started with
  `python3 udo_dash.py [--port N] [--no-open]`. Binds to `127.0.0.1` and opens the
  browser unless `--no-open`.
- **Page:** one `index.html` with inline CSS and plain JavaScript, no libraries.

Python and this structure were the builder's recommendation, and the owner
accepted them along with the folder.

### Server rules

- Runs `udo` with an argument list, never through a shell.
- Only ever runs the read-only commands listed below. There is no generic
  passthrough.
- Always passes the node explicitly (`/` or a path). Without one, udo uses the node
  of the current folder, which would silently narrow the results.
- Validates dates as `YYYY-MM-DD` and rejects session ranges over 100 days.
- Rejects requests whose `Host` is not `127.0.0.1:<port>` or `localhost:<port>`, so
  other websites can't read the data through DNS rebinding.
- If `udo` is missing or exits non-zero, returns the error text. The page shows it
  in a visible banner rather than an empty calendar.

### Endpoints and the udo commands behind them

| Endpoint | Command | Used for |
|---|---|---|
| `/api/sessions?from=&to=` | `udo session list / --from "<from> 00:00" --to "<to> 00:00" --json` | Current view; `to` is exclusive |
| `/api/tree` | `udo ls / -t --json` | To do, kinds, nearest project, colors |
| `/api/status` | `udo status --json` | Status box |
| `/api/node?path=` | `udo show <path> --json` | Side panel, on click |
| `/api/task-sessions?path=` | `udo session list <path> --all --json` | "All sessions" in the side panel, on click |

Measured on 5000 synthetic sessions (8 a day): week 14 KB in 7 ms, 42-day month grid
81 KB in 9 ms, 100 days 194 KB in 10 ms, everything 1.2 MB in 25 ms. No caching is
needed. Real rows are about 290 bytes.

### Which range each view loads

- **Week:** Monday 00:00 to the next Monday 00:00.
- **Month:** exactly the grid drawn: Monday of the week holding the 1st, to the
  Monday after the week holding the last day. That is 4 to 6 rows.
- **Day strips:** the visible window of 7, 30, 60 or 100 days. 100 is the maximum,
  in the UI and on the server.

## Data rules

These come from checking real udo output. Getting them wrong produces wrong totals.

- **Clip sessions to the range.** A session across midnight is returned by the
  queries for both days, each time with its full `minutes`. Clip with `start` and
  `end`, and draw it as one piece per day.
- **Compute durations from `start` and `end`, not `minutes`.** Session `minutes` drop
  the seconds, so many short sessions undercount. On one measured day the rows added up to
  470 minutes, the timestamps to 475.56, and `udo stats` reports 475. Sum seconds,
  then round down when displaying a total.
- **Running sessions have `end: null`.** Treat the end as now, and let the bar grow.
- **`path` can be null** when a task was removed. `--deleted` is not used, but don't
  crash if it appears: skip the row.
- **Side panel figures are udo's own.** `udo show` can differ slightly from the
  calendar totals (one measured task: `show` 576 minutes, `stats` 578). Show what `udo show`
  returns; don't reconcile them here.
- **Nearest container** is the task path's direct parent. A task at the root has
  none.
- **Colour group** is the nearest ancestor of kind `project`. If there is none, it's
  the workspace; if there's no workspace either, it's a neutral "no project" group.

## Page layout, top to bottom

1. **To do** section (larger text, prominent), with the **Status** box beside it in a
   column as wide as the side panel.
2. **Bar:** view tabs (Week, Month, Day strips), ‹ › navigation, a **Now** button
   (dimmed when already there), period label, and the total on the right.
3. **Query line:** small grey text with the udo command run and its size. Useful
   while this is a sketchpad.
4. **Legend.**
5. **Main view**, with the **side panel** on the right (310 px, stays in view while
   scrolling).

The page opens on Week at the current week.

## To do

- Lists tasks whose status isn't `done`, sorted by due date. Tasks without a due date
  go last with "no due date".
- Each row: task name, nearest container (muted), due date, relative time, and time
  left against the estimate ("1h19 left", "1m over", "no estimate").
- **Overdue:** red triangle and "overdue, 4 days ago".
- **Due in under 24 hours:** orange triangle and "due in 21h". This updates without a
  reload.
- Warnings always pair icon and text, never color alone.
- Clicking a row selects the task and highlights it.

## Status

- While a timer runs: "Running", the task, its nearest container, elapsed time and when
  it started. Otherwise "Not timing anything".
- `udo status` gives only the task's name. If exactly one task has that name, the box
  shows its container and clicking it selects and highlights the task. If not, the name
  is still shown, without a link.
- Checked once a minute as well as on navigation and window focus, because a timer can
  start or stop elsewhere while the page stays open. A change reloads the view.

## Views

### Week

- Seven columns, Monday first; each header shows the day and its total. The total
  follows the highlight.
- Vertical axis by real time, always 00:00 to 24:00. It never adapts to the
  week's sessions, because a changing axis makes the calendar jump while navigating.
- The hour height scales so the whole dashboard fits one browser height, between 16 and
  38.75 px per hour. Below 16 px the page scrolls instead, so sessions stay readable. A
  long side panel scrolls inside itself rather than making the page taller.
- Sessions are blocks at their real time.
- Labels: task name; nearest container as a second line if the block is at least
  28 px tall; only the task name from 13 px; none below that.
- Click a block: if its project isn't highlighted, highlight the project and show it
  in the panel. If it is, show that task and session in the panel.
- Click a day header: expand that column (3× width), add times to the labels, show
  the day in the panel. Click again to collapse.

### Month

- Monday-first grid, days of other months dimmed but usable. Cells at least 96 px
  tall.
- Each cell: date, total, thin stacked bar split by color. Full bar width is 8 hours.
- The total in the bar counts only days of that month, not the dimmed ones.
- Click a day with sessions: outline it and open a full-width panel under its week
  row with a 24-hour strip and a session list. Also show the day in the side panel.
  Click again to close.
- A session in the strip fills the side panel only. A session in the list also
  highlights its task.

### Day strips

- One row per day, newest first, 32 px tall, midnight to midnight.
- A heading and a heavier line wherever the month changes.
- Range buttons 7, 30, 60, 100 days, default 30. ‹ › page by the range size, never
  past today.
- Scale above and below the rows; the top one stays visible while scrolling.
- Labels: task name on the first line and nearest container on the second. The task
  name shows whole or not at all; the container may end in "…".
- Click a session: side panel only, no highlight change. Click a day label: the day in
  the side panel.

#### Zoom and pan (day strips only)

- **Zoom:** Ctrl+scroll or trackpad pinch (browsers report pinch as Ctrl+scroll),
  anchored at the cursor. From the full day down to a 1-hour window.
- The scale adapts (`00, 03, 06` to `16:30, 17:00`). Sessions outside the window are
  cut off at its edge, and labels refit.
- **Pan, once zoomed:** drag, swipe sideways, or Shift+scroll. Stops at 00:00 and
  24:00. A drag must not count as a click on a session.
- Plain vertical scrolling always moves the page.
- A "Reset zoom" button and the visible time range appear while zoomed.
- Don't replace the session elements while zooming. Removing the element under the
  cursor ends a pinch gesture. Update positions in place.

## Highlighting

There is one highlight, shared by all views, kept when switching tabs. It is either a
project or a task.

- **Project:** its tasks are shown in task colors, everything else gray.
- **Task:** only that task is colored, everything else gray.
- Gray sessions keep their labels. Only the color changes.
- The total in the bar and the day totals in the week header follow the highlight.
- The legend shows the project and its tasks in range, plus "Show all ✕".
- **Sets the highlight:** To do rows, everything clickable in the side panel
  (breadcrumb, children, "worked on", session lists), session lists under a month day,
  the legend, and project selection by a week block.
- **Clicking a session bar in day strips or the month strip:** never starts a
  highlight. If one is active and the session is grayed out, it moves to that session's
  project (or to the task itself if it has no project), and the panel shows the session.
  A colored session leaves the highlight as it is. A grayed-out sibling task in the week
  view behaves the same way.
- Clicking the workspace clears the highlight.
- A session picked from a side-panel list also moves the view to that session's date.

## Esc

One step back per press, in this order:

1. Highlighted task: highlight its project instead and show the project in the panel.
2. Project highlighted while the panel shows one of its tasks: show the project in the
   panel, keep the highlight.
3. Highlighted project (or a task with no project): remove the highlight and close the
   panel.
4. A panel with no highlight: close it.
5. An open day: close it.
6. In day strips only: reset the zoom.

## Side panel

Empty state: "Click a session, day or project to see details here."

- **Day:** tracked, sessions, first start, last end; "worked on" by task; session list.
- **Task:** breadcrumb, name, description, status, warning chip if overdue or due
  soon; "this session" (date, time, length) if a session was clicked; due, tracked,
  sessions, estimate; a tracked-vs-estimate bar; all its sessions.
- **Project or workspace:** breadcrumb, name, kind, tracked, sessions, tasks, estimated
  total, left on open tasks, tasks over estimate; done tasks tracked vs estimate;
  children with status and time; its folder.

## Color

From the validated default palette of the dataviz method. All colors are CSS variables
with light and dark values chosen by `prefers-color-scheme`.

| Role | Light | Dark |
|---|---|---|
| Project 1, blue | `#2a78d6` | `#3987e5` |
| Project 2, orange | `#eb6834` | `#d95926` |
| Project 3, aqua | `#1baf7a` | `#199e70` |
| Task 1, yellow | `#eda100` | `#c98500` |
| Task 2, magenta | `#e87ba4` | `#d55181` |
| Task 3, green | `#008300` | `#008300` |
| Task 4, violet | `#6250d6` | `#9085e9` |
| Task 5, red | `#e34948` | `#e66767` |
| Gray (not highlighted) | `#dddcd5` | `#383835` |
| Overdue icon | `#d03b3b` | `#d03b3b` |
| Due soon icon | `#ec835a` | `#ec835a` |

White text on fills, except dark text on yellow in light mode. Remaining surface and
ink values are in the prototype's CSS.

The validator passed blue, orange and aqua on all pairs, and the five task colors on
adjacent pairs, in both modes. Aqua and two task colors are below 3:1 on the light
surface, which labels and hover text make up for.

**Colors follow the entity,** not its position in the current range:

- Projects: sorted by path, in that order through the palette's 8 slots (the table's
  three, then yellow, magenta, green, violet, red).
- Tasks within a project: sorted by name in natural order, in that order through the
  five task colors. This repeats after five; names on the blocks and in the legend tell
  repeats apart.

## Interaction details

- Hovering a session or day cell shows a tooltip: task, project, time and length.
- Re-fetch the current view's data on navigation and when the window regains focus.
- Once a minute, redraw time-based things (warnings, running session). The only query
  this runs is the status check.

## Prototype differences

The prototype's behaviour stands, except:

- **Data:** real queries instead of pasted data and simulated loading.
- **Removed:** the "Preview warning" button and the explanatory heading.
- **Week axis:** the prototype is fixed to 08:00 to 24:00, which would hide earlier
  sessions. The real one always shows the whole day, at the same px per hour.
- **Totals:** from timestamps, per "Data rules". So they differ from the prototype by a
  few minutes.
- **Cross-midnight sessions and running sessions:** handled here. The prototype has
  neither.
- **Task colors:** assigned per "Color", so some differ from the prototype.

## Testing

- **Server:** `unittest` with a fake `udo` script on `PATH`: date validation, the
  100-day cap, `Host` check, error handling, exact arguments passed to udo.
- **Page logic:** clipping, totals, Esc steps and colors should be testable without a
  browser. The builder decides how, without adding a dependency.
- **By hand, not yet checked in the prototype with real input:** Ctrl+scroll and pinch
  with a real mouse and trackpad, drag, hover tooltips, light mode. macOS Accessibility
  zoom, if set to Ctrl+scroll, takes the gesture first.

## Findings for udo (#84)

Nothing to change for this dashboard, but worth carrying over:

- Session `minutes`, `udo show` and `udo stats` can disagree by minutes, because of
  where seconds are dropped.
- A session across midnight is returned with full `minutes` by range queries.
- `udo ls` JSON has no node IDs, so colors here key on paths and names. Renames or new
  siblings can shift a color.

## Left to the builder

- Code structure inside the two files.
- The exact tick steps, zoom speed and tooltip placement, as long as they behave as
  described; the prototype's values are a good start.
- The default port.
- How page logic is tested, within the no-dependency rule.
