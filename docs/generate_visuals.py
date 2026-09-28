#!/usr/bin/env python3
"""Emit the four README figures as SVG, with every number from results/*.json, git history or the code.

No plotting library. Each figure is 1200 units wide and no text is under 23 units, so the
smallest type stays about 12px at 75% browser zoom in GitHub's 837px column. Scores in
results/*.json are audited on every build, history_check() recomputes the earlier run averages
from git, and code_check() reads the two code values the pipeline figure states back from the
source. Any disagreement stops the build.
"""
import glob
import html
import json
import math
import os
import re
import statistics
import subprocess
import sys
from decimal import ROUND_HALF_DOWN, ROUND_HALF_EVEN, Decimal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from svgkit import (AQUA, AQUA_T, ARROW, BG1, BLUE, BLUE_T, FAINT, GRID, INK, INK2, INK3, MONO, MUTE,  # noqa: E402
                    ORANGE, ORANGE_T, OUTPUT, PANEL, PANEL_EDGE, RECORD, RECORD_EDGE, SANS, STROKE, VIOLET,
                    VIOLET_T, backdrop)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

VW = 1200  # viewBox width of every figure
MIN_SIZE = 23  # smallest font size allowed, per 1200 units of width
# Counts the figure copy states as fact. audit() stops the build if results/ disagrees with any of them.
N_CONFIGS = 10  # role configs, one results/*.json file each
SLATE_SIZE = 10  # candidates in each recorded slate
N_SEATS = N_CONFIGS * SLATE_SIZE  # recorded seats across all configs
HARD_RATE_TOL = 0.005  # stored pass rates may be rounded to two places; one flipped seat moves a rate by 1 / SLATE_SIZE

# Earlier recorded averages, each the exact mean of results/*.json average_final_score at its commit.
# history_check() recomputes every one with `git show` and stops the build if one disagrees.
# Run 1 predates the first commit and has no results file, so it is not drawn.
# RUN_4_SCORES holds the ten per-config scores of the Run 4 code's own recorded run (652bc29), exactly.
# history_check() compares each with git. Their mean is Run 4's average and their spread is the hero's range.
RUN_4_SCORES = {"anthropology": 206 / 3, "bankers": 271 / 3, "biology_expert": 521 / 6, "doctors_md": 87.0,
                "junior_corporate_lawyer": 274 / 3, "mathematics_phd": 359 / 4, "mechanical_engineers": 92.0,
                "quantitative_finance": 541 / 6, "radiology": 277 / 3, "tax_lawyer": 265 / 3}
HISTORY = [  # (x-axis label, commit, exact mean, note lines, grader-guided)
    ("Run 2", "0341cfa", 1043 / 20, ["Vector top 200", "LLM checks", "hard criteria"], False),  # 52.15
    ("Run 3", "170b1a9", 200 / 3, ["Vector top 200", "plus database", "filters"], False),  # 66.67
    ("Run 4", "652bc29", sum(RUN_4_SCORES.values()) / len(RUN_4_SCORES),  # 87.675, the code's own run (code 40b6df5)
     ["Exhaustive", "scans and an", "LLM judge"], False),
    ("Resubmitted", "7423943", 1073 / 12, ["Grader-guided", "resubmission"], True),  # 89.42
]
COMMITTED = HISTORY[2]  # the Run 4 code's own recorded run, the number the page leads with
RUN_5_NOTE = ["Grader-guided,", "standards not", "in the code"]  # Run 5 is the live results/*.json

# The hero's ± is a 95% t-interval of the mean over the ten configs, t(0.975, 9) * s / sqrt(10), where s is
# the sample standard deviation of the ten per-config averages. Its width comes from how much the ten roles differ,
# and it is a range for the mean, so single roles can sit well outside it (Run 4's Anthropology is 68.7).
T_975_9 = 2.262  # Student's t, two-sided 95%, 9 degrees of freedom

# Code values the pipeline figure states. code_check() reads both back from the source.
CAP_RANGE = (250, 550)  # smallest and largest pool cap in pool.py POOL_BUILDERS, unchanged since 40b6df5
PIN_MIN = 85  # selection.py pins live scores at or above this; hard-coded in 40b6df5, the PIN_MIN default since 9cbae95


def tenth(x):
    """x to one decimal as text, nearest with exact halves rounded down, after clearing float noise.

    The README states this rule. results/ averages exactly 1807/20 = 90.35 and Run 2 exactly
    1043/20 = 52.15, and both print rounded down, as 90.3 and 52.1.
    """
    clean = Decimal(repr(x)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_EVEN)
    return str(clean.quantize(Decimal("0.1"), rounding=ROUND_HALF_DOWN))


def half_width(values):
    """Half-width of the 95% t-interval of the mean of values, using the sample standard deviation."""
    if len(values) != N_CONFIGS:
        raise SystemExit(f"COUNT FAIL: the range needs {N_CONFIGS} per-config averages, got {len(values)}")
    return T_975_9 * statistics.stdev(values) / math.sqrt(len(values))


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
    """One figure on the gradient canvas. Every text passes the size floor and the fit guard before it is emitted."""

    def __init__(self, uid, h, alt):
        self.uid, self.h, self.alt, self.parts = uid, h, alt, []

    def text(self, x, y, runs, size, fill=INK, anchor="start", bold=False, frame=None, pad=16, halo=False):
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
        if halo:  # an outline in the canvas colour (BG1) keeps gridlines from running through the label
            attrs += f' stroke="{BG1}" stroke-width="8" stroke-linejoin="round" paint-order="stroke"'
        self.parts.append(f"<text {attrs}>{body}</text>")

    def rect(self, x, y, w, h, fill=PANEL, stroke=PANEL_EDGE, sw=1.5, opacity=None):
        op = "" if opacity is None else f' fill-opacity="{opacity:g}"'
        self.parts.append(f'<rect x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" fill="{fill}"{op} stroke="{stroke}" '
                          f'stroke-width="{sw}"/>')

    def line(self, x1, y1, x2, y2, stroke=GRID, sw=1.5, dash=""):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.parts.append(f'<line x1="{x1:g}" y1="{y1:g}" x2="{x2:g}" y2="{y2:g}" stroke="{stroke}" stroke-width="{sw}"{d}/>')

    def arrow(self, d, col=ARROW):
        head = {ARROW: "ah", AQUA: "ahg"}[col]  # svgkit.backdrop() defines an arrowhead in these two colours only
        self.parts.append(f'<path d="{d}" fill="none" stroke="{col}" stroke-width="2" marker-end="url(#{head}{self.uid})"/>')

    def svg(self):
        head = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {VW} {self.h}" width="{VW}" height="{self.h}" '
                f'role="img" aria-label="{html.escape(self.alt)}" font-family="{SANS}" '
                'style="font-variant-numeric: tabular-nums">\n' + backdrop(self.uid, VW, self.h))
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


def _git(*args):
    return subprocess.run(["git", "-C", ROOT, *args], capture_output=True, text=True, check=True).stdout


def history_check():
    """Recompute each HISTORY average and each RUN_4_SCORES value from git, and stop if one disagrees.

    Without git, or in a shallow clone or source archive that lacks a commit, the check is skipped
    with a warning, since the constants still carry their commits. A mismatch always stops the build.
    """
    bad, skipped = [], []
    for label, sha, mean, _, _ in HISTORY:
        try:
            names = [n for n in _git("ls-tree", "--name-only", sha, "results/").split() if n.endswith(".json")]
            blobs = {os.path.basename(n)[:-5]: _git("show", f"{sha}:{n}") for n in names}
        except (OSError, subprocess.CalledProcessError) as e:
            skipped.append(f"{label} ({sha}, {type(e).__name__})")
            continue
        try:
            scores = {k: json.loads(b)["eval_result"]["average_final_score"] for k, b in blobs.items()}
        except (KeyError, TypeError, ValueError) as e:
            bad.append(f"{label} ({sha}): results/ at this commit lacks average_final_score ({type(e).__name__})")
            continue
        got = sum(scores.values()) / len(scores) if scores else float("nan")
        if len(scores) != N_CONFIGS or not abs(got - mean) < 1e-9:
            bad.append(f"{label} ({sha}): git has {len(scores)} configs averaging {got:.4f}, HISTORY says {mean:.4f}")
        if sha == COMMITTED[1]:  # the hero's range uses each of these scores, so check each one
            for k in sorted(set(scores) | set(RUN_4_SCORES)):
                if k not in scores or k not in RUN_4_SCORES or not abs(scores[k] - RUN_4_SCORES[k]) < 1e-9:
                    bad.append(f"{label} ({sha}): {k} is {scores.get(k)} in git, {RUN_4_SCORES.get(k)} in RUN_4_SCORES")
    if skipped:
        print("  HISTORY SKIP: this checkout cannot read " + ", ".join(skipped)
              + ". Those averages are drawn from the HISTORY constants unverified; build from a full clone to check them.")
    if bad:
        raise SystemExit("HISTORY FAIL: an earlier average in the figures no longer matches git.\n  - " + "\n  - ".join(bad))


def code_check():
    """Stop if pool.py's pool caps or selection.py's pin threshold differ from what the pipeline figure states."""
    pool = open(os.path.join(ROOT, "pool.py"), encoding="utf-8").read()
    sel = open(os.path.join(ROOT, "selection.py"), encoding="utf-8").read()
    caps = [int(c) for c in re.findall(r'"\w+\.yml": \(pool_\w+, (\d+)\)', pool)]
    pin = re.search(r'os\.environ\.get\("PIN_MIN", "(\d+)"\)', sel)
    problems = []
    if len(caps) != N_CONFIGS or (min(caps), max(caps)) != CAP_RANGE:
        problems.append(f"pool.py pool caps are {caps}, the figure states {CAP_RANGE[0]} to {CAP_RANGE[1]}")
    if not pin or int(pin.group(1)) != PIN_MIN:
        problems.append(f"selection.py pins at {pin.group(1) if pin else 'an unreadable default'}, the figure states {PIN_MIN}")
    if problems:
        raise SystemExit("CODE FAIL: the pipeline figure no longer matches the code.\n  - " + "\n  - ".join(problems))


def hero(a):
    """Title, subtitle, the two averages with their ranges (the committed pipeline's first), then the final slates."""
    ten = _count(SLATE_SIZE)
    own = f"{tenth(COMMITTED[2])} ± {tenth(half_width(list(RUN_4_SCORES.values())))}"
    final = f"{tenth(a['overall'])} ± {tenth(half_width([r['avg'] for r in a['rows']]))}"
    alt = (f"Candidate search over a Turbopuffer database of profiles. The pipeline as committed averaged {own} "
           f"across {N_CONFIGS} configs ({COMMITTED[0]}). Grader-guided resubmission raised the average to {final} "
           f"(Run 5). Each ± is a 95% t-interval for the mean of these ten roles, with no claim about unseen roles. "
           f"In the final submitted slates, all {a['n_hard']} configs pass every hard criterion, all "
           f"{a['n80']} score 80 or above, {a['n90']} score 90 or above, and there are {a['hard_fail_seats']} hard "
           f"failures in {N_SEATS} recorded seats.")
    f = Fig("h", 704, alt)
    f.text(40, 84, "Candidate search", 44, bold=True)
    f.text(40, 128, f"Scans a Turbopuffer database of profiles to pick {ten} candidates per role,", 24, INK3)
    f.text(40, 160, "checked against hard requirements and soft preferences.", 24, INK3)
    top, h, cw = 196, 176, 560  # the two averages, the committed pipeline's first and larger
    f.rect(40, top, 2 * cw, h)
    f.line(40 + cw, top + 24, 40 + cw, top + h - 24, PANEL_EDGE)
    heads = [(own, 56, VIOLET_T, ["Pipeline as committed,", f"{COMMITTED[0]} average over {N_CONFIGS} configs"]),
             (final, 44, INK, ["After grader-guided resubmission,", f"Run 5 average over {N_CONFIGS} configs"])]
    for i, (value, size, col, label) in enumerate(heads):
        cx = 40 + i * cw
        f.text(cx + 24, top + 76, value, size, col, bold=True, frame=(cx, top, cw, h))
        for j, part in enumerate(label):
            f.text(cx + 24, top + 118 + 30 * j, part, 23, INK3, frame=(cx, top, cw, h))
    f.text(40, top + h + 32, "± is a 95% t-interval for the mean of these ten roles, with no claim about unseen roles.",
           23, MUTE)
    top2, h2, cw2 = 468, 196, 280  # four facts that describe the final submitted slates only
    f.text(40, top2 - 16, [("Final submitted slates · ", False), ("results/*.json", True)], 23, MUTE)
    f.rect(40, top2, 4 * cw2, h2)
    stats = [(f"{a['n_hard']} / {N_CONFIGS}", ["Configs", "passing every", "hard criterion"]),
             (f"{a['n80']} / {N_CONFIGS}", ["Configs at", "80 or above"]),
             (f"{a['n90']} / {N_CONFIGS}", ["Configs at", "90 or above"]),
             (f"{a['hard_fail_seats']}", ["Hard failures", f"in {N_SEATS}", "recorded seats"])]
    for i, (value, label) in enumerate(stats):
        cx = 40 + i * cw2
        if i:
            f.line(cx, top2 + 24, cx, top2 + h2 - 24, PANEL_EDGE)
        f.text(cx + 24, top2 + 55, value, 40, AQUA, bold=True, frame=(cx, top2, cw2, h2))
        for j, part in enumerate(label):
            f.text(cx + 24, top2 + 98 + 30 * j, part, 23, INK3, frame=(cx, top2, cw2, h2))
    return f.svg()


def pipeline(a):
    """Five stages in reading order, then the three places a run is recorded."""
    ten, table, (lo, hi) = _count(SLATE_SIZE), f"{tenth(HISTORY[0][2])} to {tenth(a['overall'])}", CAP_RANGE
    alt = (f"Candidate search pipeline over a Turbopuffer database, in five stages. Scan pages in id order through "
           "every profile that matches the role's attribute filter. Prescreen checks degree, school, field and dates, "
           f"ranks by keywords and keeps {lo} to {hi} candidates per role. Judge has GPT-4o-mini score hard and soft "
           "criteria from the profile text alone, without live scores. Select seats candidates the live grader already "
           f"scored {PIN_MIN} or above first, then judged hard passes. Submit sends {ten} candidates per role to the "
           f"live grader. Outputs are results/*.json, a submission ledger that drops hard failures and pins {PIN_MIN}+ "
           f"scorers, and a run table with averages from {table}.")
    f = Fig("p", 960, alt)
    f.text(40, 80, "Candidate search pipeline", 36, bold=True)
    f.text(40, 120, f"From a Turbopuffer database to {ten} submitted candidates per role.", 24, INK3)
    stages = [("Scan", "Pages in id order through every profile that",
               "matches the role's attribute filter (pool.py)."),
              ("Prescreen", "Degree, school, field and date checks, then keyword",
               f"ranking, capped at {lo} to {hi} per role (pool.py)."),
              ("Judge", "GPT-4o-mini scores hard and soft criteria from the profile",
               "text alone, one candidate per call, without live scores."),
              ("Select", "Seats go first to candidates the live grader already",
               f"scored {PIN_MIN}+, then to judged hard passes (selection.py)."),
              ("Submit", f"Sends {ten} candidates per role to the live grader,",
               "then records the scores and archives the response.")]
    # Box fill, edge and name colour per stage. Submit, which records the run, gets the lighter RECORD box.
    grad = f"url(#nd{f.uid})"
    looks = {"Scan": (grad, VIOLET, VIOLET_T), "Prescreen": (grad, BLUE, BLUE_T), "Judge": (grad, ORANGE, ORANGE_T),
             "Select": (grad, AQUA, AQUA_T), "Submit": (RECORD, RECORD_EDGE, INK)}
    for i, (name, line1, line2) in enumerate(stages):
        top = 152 + i * 120
        fill, edge, ink = looks[name]
        f.rect(40, top, 1120, 96, fill, edge)
        f.text(64, top + 57, name, 26, ink, bold=True, frame=(40, top, 284, 96))
        f.text(324, top + 39, line1, 23, MUTE, frame=(308, top, 852, 96))
        f.text(324, top + 69, line2, 23, MUTE, frame=(308, top, 852, 96))
        if i < len(stages) - 1:
            f.arrow(f"M 600 {top + 96} V {top + 118}", AQUA if name == "Select" else ARROW)
    rec_bottom, oy, oh, gut = 152 + 4 * 120 + 96, 776, 136, 24
    ow = (1120 - 2 * gut) / 3
    centers = [40 + ow / 2 + k * (ow + gut) for k in range(3)]
    f.line(600, rec_bottom, 600, 752, ARROW, 2)
    f.line(centers[0], 752, centers[-1], 752, ARROW, 2)
    outs = [([("results/*.json", True)], ["One recorded evaluation", "per config"]),
            ("Submission ledger", ["Drops hard failures,", f"pins {PIN_MIN}+ scorers"]),
            ("Run table", ["Average score", table])]
    for k, (heading, desc) in enumerate(outs):
        bx = 40 + k * (ow + gut)
        frame = (bx, oy, ow, oh)
        f.arrow(f"M {centers[k]:g} 752 V {oy - 2}")
        f.rect(bx, oy, ow, oh, OUTPUT, ORANGE)
        f.text(bx + 24, oy + 44, heading, 26, ORANGE_T, bold=True, frame=frame)
        for j, part in enumerate(desc):
            f.text(bx + 24, oy + 82 + 30 * j, part, 23, MUTE, frame=frame)
    return f.svg()


def progression(a):
    """Recorded averages by run on a 0 to 100 scale. Hollow points on a dashed line are grader-guided resubmissions."""
    runs = HISTORY + [("Run 5", "HEAD", a["overall"], RUN_5_NOTE, True)]
    vals = [tenth(mean) for _, _, mean, _, _ in runs]
    lead = runs.index(COMMITTED)
    alt = (f"Average final score by run. Runs 2 and 3 retrieved a vector top 200 and averaged {vals[0]} and {vals[1]}. "
           f"Run 4, the pipeline as committed with exhaustive scans and an LLM judge, averaged {vals[lead]}. "
           f"Grader-guided resubmission then reached {vals[3]}, and Run 5 reached {vals[4]}. "
           "Run 1 has no results file and is not drawn.")
    f = Fig("r", 704, alt)
    y0, y1 = 384, 168  # plot bottom (score 0) and top (score 100)
    ys = lambda v: y0 - v / 100 * (y0 - y1)  # noqa: E731
    f.text(40, 80, "Average final score by run", 36, bold=True)
    f.text(40, 128, "Average final score", 23, MUTE)
    for t in (0, 50, 100):
        f.line(96, ys(t), 1160, ys(t))
        f.text(80, ys(t) + 8, str(t), 23, FAINT, anchor="end")
    # No 90 reference line here: the grader-guided points sit within a unit of it and its dashes would hide theirs.
    pts = [(152 + 224 * i, ys(mean)) for i, (_, _, mean, _, _) in enumerate(runs)]
    first_guided = next(i for i, r in enumerate(runs) if r[4])
    for seg, dash in ((pts[:first_guided], ""), (pts[first_guided - 1:], ' stroke-dasharray="8 7"')):
        f.parts.append('<polyline points="' + " ".join(f"{x:g},{y:.1f}" for x, y in seg)
                       + f'" fill="none" stroke="{STROKE}" stroke-width="2.5"{dash}/>')
    for i, ((name, _, mean, note, guided), (x, y)) in enumerate(zip(runs, pts)):
        col = AQUA if mean >= 90 else (VIOLET if i >= lead else BLUE)  # aqua at 90 or above, violet from Run 4 on
        if guided:  # hollow: a grader-guided resubmission, not the committed pipeline
            f.parts.append(f'<circle cx="{x:g}" cy="{y:.1f}" r="7" fill="{BG1}" stroke="{col}" stroke-width="3"/>')
        else:
            f.parts.append(f'<circle cx="{x:g}" cy="{y:.1f}" r="7" fill="{col}"/>')
        f.text(x, y - 20, vals[i], 26, VIOLET_T if i == lead else INK, "middle", bold=True, halo=True)
        frame = (x - 112, 0, 224, f.h)
        f.text(x, 428, name, 24, INK2, anchor="middle", frame=frame)
        for j, part in enumerate(note):
            f.text(x, 460 + 30 * j, part, 23, MUTE, "middle", frame=frame)
    f.text(600, 594, "Recorded run", 23, MUTE, "middle")
    f.text(40, 636, "Hollow points are grader-guided resubmissions. Run 1 has no results file.", 23, MUTE)
    f.text(40, 668, [("Runs 2 to 4 and the resubmission come from git history, Run 5 from ", False),
                     ("results/*.json", True), (".", False)], 23, MUTE)
    return f.svg()


def scores(a):
    """Each config's final score as a bar on a 0 to 100 scale, in descending order, with the 90 line."""
    rows, n = a["rows"], N_CONFIGS
    if a["n_hard"] != n or a["n80"] != n:
        raise SystemExit("the copy says every config passes its hard criteria and clears 80; results/ disagrees")
    f = Fig("s", 808, (f"Recorded eval scores of the final submitted slates, after grader-guided resubmission, for all "
                       f"{_count(n)} role configs, from results/. {_count(a['n90']).capitalize()} of {_count(n)} score 90 "
                       f"or above, all {_count(n)} score 80 or above, and every hard criterion passes at 100 percent."))
    x0, x1, top, pitch, bar = 424, 1084, 160, 48, 28
    xs = lambda v: x0 + v / 100 * (x1 - x0)  # noqa: E731
    bottom = top + pitch * (n - 1) + bar
    f.text(40, 80, "Final submitted slates by role", 36, bold=True)
    f.text(40, 136, "Role", 23, MUTE)
    f.text(x0, 136, "Final evaluation score (0 to 100)", 23, MUTE)
    f.text(xs(90), 136, "90", 23, FAINT, "middle")
    for t in range(0, 101, 20):
        f.line(xs(t), 150, xs(t), bottom + 12)
        f.text(xs(t), bottom + 44, str(t), 23, FAINT, "middle")
    for i, r in enumerate(rows):
        y = top + i * pitch
        f.text(40, y + 22, r["name"], 24, INK3, frame=(24, 0, x0 - 24, f.h))
        f.rect(x0, y, xs(r["avg"]) - x0, bar, AQUA if r["avg"] >= 90 else BLUE, "none", 0, opacity=0.9)
    f.line(xs(90), 148, xs(90), bottom + 12, FAINT, 1.5, "6 6")
    for i, r in enumerate(rows):
        f.text(xs(r["avg"]) + 16, top + i * pitch + 23, tenth(r["avg"]), 26, bold=True, halo=True)
    f.text(40, bottom + 96, f"Final slates after grader-guided resubmission, {_count(SLATE_SIZE)} candidates per config.",
           23, MUTE)
    f.text(40, bottom + 126, f"{a['n90']}/{n} at 90 or above, {a['n80']}/{n} at 80 or above, "
                             "and every hard criterion passes at 100%.", 23, MUTE)
    f.text(40, bottom + 156, [("Recorded live evaluations in ", False), ("results/*.json", True), (".", False)], 23, MUTE)
    return f.svg()


if __name__ == "__main__":
    a = audit()
    history_check()
    code_check()
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
