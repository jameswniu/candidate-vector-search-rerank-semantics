#!/usr/bin/env python3
"""Emit the four README figures as SVG, with every score derived from results/*.json.

No plotting library. Each figure is 1200 units wide and no text is under 23 units, so the
smallest type stays about 12px at 75% browser zoom in GitHub's 837px column.
"""
import glob
import html
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from svgkit import MONO, SANS  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Flat palette. Contrast on the canvas: TEXT 16.8:1, TEXT2 10.0:1, ACCENT 8.9:1, DATA2 6.0:1.
CANVAS, PANEL, BORDER = "#101418", "#181e24", "#46515c"
TEXT, TEXT2 = "#f2f4f6", "#b6c0ca"
ACCENT, DATA2 = "#8bb8e8", "#8795a3"

VW = 1200  # viewBox width of every figure
MIN_SIZE = 23  # smallest font size allowed, per 1200 units of width
CORPUS = "194K"  # profiles in the index, as stated in the README; not part of results/
# Counts the figure copy states as fact. audit() stops the build if results/ disagrees with any of them.
N_CONFIGS = 10  # role configs, one results/*.json file each
SLATE_SIZE = 10  # candidates in each recorded slate
N_SEATS = N_CONFIGS * SLATE_SIZE  # recorded seats across all configs
HARD_RATE_TOL = 0.005  # stored pass rates may be rounded to two places; one flipped seat moves a rate by 1 / SLATE_SIZE

# Fit guard. Per-char advances in em are deliberately generous (mono 0.62, sans 0.56, sans bold
# 0.60), and so are ascent and descent, so SF, Menlo, Courier New, Helvetica and Arial all land
# inside the modelled box. A text that would not clear its frame by `pad` stops the build loudly.
ADV = {"mono": 0.62, "sans": 0.56, "sans_bold": 0.60}
ASC, DESC = 0.96, 0.30


def _fit(frame, x, y, w, size, anchor, pad, label):
    """Raise unless a text w wide at (x, y) clears frame (x, y, w, h) by pad on every side."""
    fx, fy, fw, fh = frame
    left = {"start": x, "middle": x - w / 2, "end": x - w}[anchor]
    slack = min(left - fx, fx + fw - (left + w), y - ASC * size - fy, fy + fh - (y + DESC * size)) - pad
    if slack < 0:
        raise SystemExit(f"FIT FAIL: {label!r} ({size}) overflows its frame {frame} by {-slack:.1f} (pad {pad})")


class Fig:
    """One figure on a flat canvas. Every text passes the size floor and the fit guard before it is emitted."""

    def __init__(self, uid, h, alt):
        self.uid, self.h, self.alt, self.parts = uid, h, alt, []

    def text(self, x, y, runs, size, fill=TEXT, anchor="start", bold=False, frame=None, pad=16, halo=False):
        """One line of text. runs is a string, or a list of (text, is_code) pieces; code is set in mono."""
        runs = [(runs, False)] if isinstance(runs, str) else runs
        label = "".join(s for s, _ in runs)
        if size * 1200 / VW < MIN_SIZE:
            raise SystemExit(f"SIZE FAIL: {label!r} is {size} units, under {MIN_SIZE} per 1200")
        w = sum(len(s) * size * ADV["mono" if code else ("sans_bold" if bold else "sans")] for s, code in runs)
        _fit(frame or (0, 0, VW, self.h), x, y, w, size, anchor, pad, label)
        body = "".join(f'<tspan font-family="{MONO}">{html.escape(s)}</tspan>' if code else html.escape(s)
                       for s, code in runs)
        attrs = f'x="{x:g}" y="{y:g}" fill="{fill}" font-size="{size}"'
        attrs += "" if anchor == "start" else f' text-anchor="{anchor}"'
        attrs += ' font-weight="700"' if bold else ""
        if halo:  # a canvas-coloured outline keeps gridlines from running through the label
            attrs += f' stroke="{CANVAS}" stroke-width="8" stroke-linejoin="round" paint-order="stroke"'
        self.parts.append(f"<text {attrs}>{body}</text>")

    def rect(self, x, y, w, h, fill=PANEL, stroke=BORDER, sw=1.5):
        self.parts.append(f'<rect x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')

    def line(self, x1, y1, x2, y2, stroke=BORDER, sw=1.5, dash=""):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.parts.append(f'<line x1="{x1:g}" y1="{y1:g}" x2="{x2:g}" y2="{y2:g}" stroke="{stroke}" stroke-width="{sw}"{d}/>')

    def arrow(self, d):
        self.parts.append(f'<path d="{d}" fill="none" stroke="{DATA2}" stroke-width="2" marker-end="url(#ah{self.uid})"/>')

    def svg(self):
        head = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {VW} {self.h}" width="{VW}" height="{self.h}" '
                f'role="img" aria-label="{html.escape(self.alt)}" font-family="{SANS}" '
                'style="font-variant-numeric: tabular-nums">\n'
                f'<defs><marker id="ah{self.uid}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" '
                f'orient="auto"><path d="M 0 0 L 10 5 L 0 10 z" fill="{DATA2}"/></marker></defs>\n'
                f'<rect width="{VW}" height="{self.h}" fill="{CANVAS}"/>\n')
        return head + "\n".join(self.parts) + "\n</svg>\n"


def _num(x):
    """True for an int or a float, but not a bool."""
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _hard_check(name, ev, bad):
    """Recompute each hard criterion's pass rate from the per-candidate scores and check it against the stored rate.

    Nothing defaults to passing: every missing field or disagreement is added to bad and makes the file unusable.
    Returns ({criterion: recomputed pass rate}, seats with a hard failure), or None when the file is unusable.
    """
    start = len(bad)
    if not isinstance(ev, dict):
        bad.append(f"{name}: eval_result is missing")
        return None
    if not _num(ev.get("average_final_score")):
        bad.append(f"{name}: eval_result.average_final_score is missing")
    averages = ev.get("average_hard_scores")
    if not isinstance(averages, list) or not averages:
        bad.append(f"{name}: eval_result.average_hard_scores is missing or empty")
        averages = []
    stored = {}
    for i, h in enumerate(averages):
        h = h if isinstance(h, dict) else {}
        if not isinstance(h.get("criteria_name"), str) or not _num(h.get("pass_rate")):
            bad.append(f"{name}: eval_result.average_hard_scores[{i}] is missing criteria_name or pass_rate")
        else:
            stored[h["criteria_name"]] = h["pass_rate"]
    if len(bad) > start:  # without usable stored rates, the candidate checks would only repeat this problem
        return None
    slate = ev.get("individual_results")
    if not isinstance(slate, list) or not slate:
        bad.append(f"{name}: eval_result.individual_results is missing or empty")
        return None
    passed, fail_seats = dict.fromkeys(stored, 0), 0
    for i, r in enumerate(slate):
        scores = r.get("hard_scores") if isinstance(r, dict) else None
        if not isinstance(scores, list) or not scores:
            bad.append(f"{name}: individual_results[{i}].hard_scores is missing or empty")
            continue
        got = {}
        for j, h in enumerate(scores):
            h = h if isinstance(h, dict) else {}
            where = f"{name}: individual_results[{i}].hard_scores[{j}]"
            if not isinstance(h.get("criteria_name"), str):
                bad.append(f"{where}.criteria_name is missing")
            elif not isinstance(h.get("passes"), bool):
                bad.append(f"{where}.passes is missing or not true/false")
            else:
                got[h["criteria_name"]] = h["passes"]
        if len(got) == len(scores) and set(got) != set(stored):
            bad.append(f"{name}: individual_results[{i}].hard_scores covers {sorted(got)}, not {sorted(stored)}")
        for c in stored:
            if got.get(c) is True:
                passed[c] += 1
        if not all(got.values()):
            fail_seats += 1
    for c, rate in stored.items():
        recomputed = passed[c] / len(slate)
        if abs(recomputed - rate) > HARD_RATE_TOL:
            bad.append(f"{name}: {c} pass rate is {recomputed:.2f} from hard_scores but {rate} in average_hard_scores "
                       f"(tolerance {HARD_RATE_TOL})")
    if len(bad) > start:
        return None
    return {c: passed[c] / len(slate) for c in stored}, fail_seats


def audit():
    """Re-derive the headline numbers from the recorded evals, and stop if a count or a hard score does not hold."""
    rows, bad, off_size = [], [], []
    seats = hard_fail_seats = 0
    for f in sorted(glob.glob(os.path.join(ROOT, "results", "*.json"))):
        name = os.path.basename(f)
        d = json.load(open(f))
        checked = _hard_check(name, d.get("eval_result"), bad)
        if checked is None:
            continue
        rates, fails = checked
        ev = d["eval_result"]
        n_slate = len(ev["individual_results"])
        if n_slate != SLATE_SIZE:
            off_size.append(f"{name} has {n_slate}")
        seats += n_slate
        hard_fail_seats += fails
        rows.append(dict(name=d.get("config", name), avg=ev["average_final_score"], min_hard=min(rates.values())))
    if bad:
        raise SystemExit("SCORE FAIL: results/ is missing or contradicts the score fields the figures rely on.\n  - "
                         + "\n  - ".join(bad))
    problems = []
    if len(rows) != N_CONFIGS:
        problems.append(f"found {len(rows)} configs in results/, the figures state {N_CONFIGS} (N_CONFIGS)")
    if off_size:
        problems.append(f"every slate must hold {SLATE_SIZE} candidates (SLATE_SIZE), but " + ", ".join(off_size))
    if seats != N_SEATS:
        problems.append(f"found {seats} recorded seats, the figures state {N_SEATS} (N_SEATS)")
    if problems:
        raise SystemExit("COUNT FAIL: results/ no longer matches the counts the figures state.\n  - " + "\n  - ".join(problems))
    rows.sort(key=lambda r: -r["avg"])
    n = len(rows)
    return dict(rows=rows, n=n,
                overall=sum(r["avg"] for r in rows) / n,
                n_hard=sum(1 for r in rows if r["min_hard"] >= 1.0),
                n90=sum(1 for r in rows if r["avg"] >= 90),
                n80=sum(1 for r in rows if r["avg"] >= 80),
                seats=seats, hard_fail_seats=hard_fail_seats)


_WORDS = "zero one two three four five six seven eight nine ten eleven twelve".split()


def _count(n):
    """A count as a word for prose (zero to twelve), else its digits."""
    return _WORDS[n] if 0 <= n < len(_WORDS) else str(n)


# The first four averages are historical measurements: each is recorded in its run's README
# table and in the commit that landed that run. Only the final average is re-derived live.
RUN_HISTORY = [
    ("Run 1", 46.7, ["Strict filters", "and soft-only", "reranking"]),
    ("Run 2", 52.1, ["LLM checks", "hard criteria"]),
    ("Run 3", 66.6, ["Database", "filters"]),
    ("Run 4", 89.4, ["Exhaustive", "scans, scoring", "matched to", "eval judge"]),
]
RUN_5_NOTE = ["Wider search,", "rechecked by", "a blind judge"]


def _run(name):
    """The recorded average of one historical run."""
    return next(avg for n, avg, _ in RUN_HISTORY if n == name)


def hero(a):
    """Title, one-sentence subtitle, and one strip of five stats checked against results/."""
    ten, overall = _count(SLATE_SIZE), f"{a['overall']:.1f}"
    alt = (f"Semantic candidate search over about {CORPUS} profiles. Recorded evaluations average {overall} "
           f"across {N_CONFIGS} configs. All {a['n_hard']} configs have a 100% pass rate on every hard criterion; "
           f"all {a['n80']} score 80 or above, and {a['n90']} score 90 or above. "
           f"There are {a['hard_fail_seats']} hard failures in {N_SEATS} recorded seats.")
    f = Fig("h", 488, alt)
    f.text(40, 84, "Semantic candidate search", 44, bold=True)
    f.text(40, 128, f"Searches ~{CORPUS} profiles to produce {ten} candidates per role, checked against", 24, TEXT2)
    f.text(40, 160, "hard requirements and soft preferences.", 24, TEXT2)
    f.text(40, 216, [("Recorded evaluations · ", False), ("results/*.json", True)], 23, TEXT2)
    top, h, cw = 232, 216, 224
    f.rect(40, top, 5 * cw, h)
    stats = [(overall, ["Average final", "score across", f"{N_CONFIGS} configs"], ACCENT),
             (f"{a['n_hard']} / {N_CONFIGS}", ["Configs", "passing every", "hard criterion"], TEXT),
             (f"{a['n80']} / {N_CONFIGS}", ["Configs at", "80 or above"], TEXT),
             (f"{a['n90']} / {N_CONFIGS}", ["Configs at", "90 or above"], TEXT),
             (f"{a['hard_fail_seats']}", ["Hard failures", f"in {N_SEATS}", "recorded seats"], TEXT)]
    for i, (value, label, col) in enumerate(stats):
        cx = 40 + i * cw
        col_frame = (cx, top, cw, h)
        if i:
            f.line(cx, top + 24, cx, top + h - 24)
        f.text(cx + 24, top + 55, value, 40, col, bold=True, frame=col_frame)
        for j, part in enumerate(label):
            f.text(cx + 24, top + 98 + 30 * j, part, 23, TEXT2, frame=col_frame)
    return f.svg()


def pipeline(a):
    """Five stages in reading order, then the three places a run is recorded."""
    ten, table = _count(SLATE_SIZE), f"{_run('Run 3'):.1f} to {a['overall']:.1f}"
    alt = (f"Candidate search pipeline over about {CORPUS} profiles: Voyage-3 query vectors and exhaustive ID-ordered "
           "Turbopuffer scans; filters for degree, field, school and dates; GPT-4o-mini reranking on hard and soft "
           "criteria using the text available to the evaluation judge; blind rubric verification under standards fixed "
           f"before review; and live evaluation and archiving of {ten} candidates per role. Outputs are results/*.json, "
           f"a submission ledger that permanently excludes hard failures, and a run table showing average scores from {table}.")
    f = Fig("p", 960, alt)
    f.text(40, 80, "Candidate search pipeline", 36, bold=True)
    f.text(40, 120, f"From ~{CORPUS} profiles in Turbopuffer to {ten} verified candidates per role.", 24, TEXT2)
    stages = [("Retrieve", "Voyage-3 query vectors, plus exhaustive id-ordered scans",
               "that cover the full population matching the hard filters."),
              ("Filter", "Degree, field, school and date requirements.",
               "Exact recall against the structured hard criteria."),
              ("Rerank", "GPT-4o-mini scores hard and soft criteria using",
               "only the profile text available to the evaluation judge."),
              ("Verify", "Blind rubric-scored judge, with standards fixed before review.",
               "The judge does not see prior live scores."),
              ("Record", f"Submit {ten} candidates per role to the live endpoint.",
               "Archive the slate and the returned evaluation scores.")]
    for i, (name, line1, line2) in enumerate(stages):
        top = 152 + i * 120
        f.rect(40, top, 1120, 96)
        f.text(64, top + 57, name, 26, ACCENT if name == "Verify" else TEXT, bold=True, frame=(40, top, 284, 96))
        f.text(324, top + 39, line1, 23, TEXT2, frame=(308, top, 852, 96))
        f.text(324, top + 69, line2, 23, TEXT2, frame=(308, top, 852, 96))
        if i < len(stages) - 1:
            f.arrow(f"M 600 {top + 96} V {top + 118}")
    rec_bottom, oy, oh, gut = 152 + 4 * 120 + 96, 776, 136, 24
    ow = (1120 - 2 * gut) / 3
    centers = [40 + ow / 2 + k * (ow + gut) for k in range(3)]
    f.line(600, rec_bottom, 600, 752, DATA2, 2)
    f.line(centers[0], 752, centers[-1], 752, DATA2, 2)
    outs = [([("results/*.json", True)], ["One recorded evaluation", "per config"]),
            ("Submission ledger", ["Hard failures are", "permanently excluded."]),
            ("Run table", ["Average score", table])]
    for k, (heading, desc) in enumerate(outs):
        bx = 40 + k * (ow + gut)
        frame = (bx, oy, ow, oh)
        f.arrow(f"M {centers[k]:g} 752 V {oy - 2}")
        f.rect(bx, oy, ow, oh)
        f.text(bx + 24, oy + 44, heading, 26, bold=True, frame=frame)
        for j, part in enumerate(desc):
            f.text(bx + 24, oy + 82 + 30 * j, part, 23, TEXT2, frame=frame)
    return f.svg()


def progression(a):
    """The five recorded averages as points on a 0 to 100 scale, with the 90 line for reference."""
    final, n_hist = a["overall"], len(RUN_HISTORY)
    runs = RUN_HISTORY + [(f"Run {n_hist + 1}", final, RUN_5_NOTE)]
    f = Fig("r", 684, (f"Average eval score across the {_count(len(runs))} recorded runs, from {_run('Run 1'):.1f} with "
                       f"strict filters and a soft-only reranker to {final:.1f} with exhaustive scans and a blind re-judge"))
    y0, y1 = 384, 168  # plot bottom (score 0) and top (score 100)
    ys = lambda v: y0 - v / 100 * (y0 - y1)  # noqa: E731
    f.text(40, 80, "Average final score by run", 36, bold=True)
    f.text(40, 128, "Average final score", 23, TEXT2)
    for t in (0, 50, 100):
        f.line(96, ys(t), 1160, ys(t))
        f.text(80, ys(t) + 8, str(t), 23, TEXT2, anchor="end")
    f.line(96, ys(90), 1160, ys(90), DATA2, 1.5, "6 6")
    f.text(1160, ys(90) + 30, "90", 23, TEXT2, anchor="end")
    pts = [(152 + 224 * i, ys(avg)) for i, (_, avg, _) in enumerate(runs)]
    f.parts.append('<polyline points="' + " ".join(f"{x:g},{y:.1f}" for x, y in pts)
                   + f'" fill="none" stroke="{DATA2}" stroke-width="2.5"/>')
    for i, ((name, avg, note), (x, y)) in enumerate(zip(runs, pts)):
        col = ACCENT if i == len(runs) - 1 else DATA2
        f.parts.append(f'<circle cx="{x:g}" cy="{y:.1f}" r="7" fill="{col}"/>')
        f.text(x, y - 20, f"{avg:.1f}", 26, TEXT if col == DATA2 else ACCENT, "middle", bold=True, halo=True)
        frame = (x - 112, 0, 224, f.h)
        f.text(x, 428, name, 24, anchor="middle", frame=frame)
        for j, part in enumerate(note):
            f.text(x, 460 + 30 * j, part, 23, TEXT2, "middle", frame=frame)
    f.text(600, 594, "Recorded run", 23, TEXT2, "middle")
    f.text(40, 636, [(f"Runs 1 to {n_hist} from recorded run tables, Run {n_hist + 1} from ", False),
                     ("results/*.json", True), (".", False)], 23, TEXT2)
    return f.svg()


def scores(a):
    """Each config's final score as a bar on a 0 to 100 scale, in descending order, with the 90 line."""
    rows, n = a["rows"], N_CONFIGS
    if a["n_hard"] != n or a["n80"] != n:
        raise SystemExit("the copy says every config passes its hard criteria and clears 80; results/ disagrees")
    f = Fig("s", 800, (f"Recorded eval scores for all {_count(n)} role configs: {_count(a['n90'])} of {_count(n)} at 90 "
                       f"or above, all {_count(n)} at 80 or above, every hard criterion passing at 100 percent"))
    x0, x1, top, pitch, bar = 424, 1084, 160, 48, 28
    xs = lambda v: x0 + v / 100 * (x1 - x0)  # noqa: E731
    bottom = top + pitch * (n - 1) + bar
    f.text(40, 80, "Final evaluation score by role", 36, bold=True)
    f.text(40, 136, "Role", 23, TEXT2)
    f.text(x0, 136, "Final evaluation score (0 to 100)", 23, TEXT2)
    f.text(xs(90), 136, "90", 23, TEXT2, "middle")
    for t in range(0, 101, 20):
        f.line(xs(t), 150, xs(t), bottom + 12)
        f.text(xs(t), bottom + 44, str(t), 23, TEXT2, "middle")
    for i, r in enumerate(rows):
        y = top + i * pitch
        f.text(40, y + 22, r["name"], 24, frame=(24, 0, x0 - 24, f.h))
        f.rect(x0, y, xs(r["avg"]) - x0, bar, ACCENT if r["avg"] >= 90 else DATA2, "none", 0)
    f.line(xs(90), 148, xs(90), bottom + 12, DATA2, 1.5, "6 6")
    for i, r in enumerate(rows):
        f.text(xs(r["avg"]) + 16, top + i * pitch + 23, f"{r['avg']:.1f}", 26, bold=True, halo=True)
    f.text(40, bottom + 96, [(f"{_count(SLATE_SIZE).capitalize()} candidates per config. Recorded live evaluations: ", False),
                             ("results/*.json", True), (".", False)], 23, TEXT2)
    f.text(40, bottom + 126, f"{a['n90']}/{n} at 90 or above, {a['n80']}/{n} at 80 or above, "
                             "and every hard criterion passes at 100%.", 23, TEXT2)
    return f.svg()


if __name__ == "__main__":
    a = audit()
    os.makedirs(os.path.join(ROOT, "assets"), exist_ok=True)
    os.makedirs(os.path.join(ROOT, "docs", "figures"), exist_ok=True)
    for path, svg in [("assets/hero.svg", hero(a)),
                      ("assets/pipeline.svg", pipeline(a)),
                      ("docs/figures/config_scores.svg", scores(a)),
                      ("docs/figures/run_progression.svg", progression(a))]:
        p = os.path.join(ROOT, path)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(svg)
        print(f"  {path}  {os.path.getsize(p):,} bytes")
