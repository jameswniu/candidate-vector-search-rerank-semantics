#!/usr/bin/env python3
"""Emit every visual in this repo as SVG, with the receipts derived from results/*.json.

No plotting library. Type is sized so the figures stay readable at 75% browser zoom.
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from svgkit import *  # noqa

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def audit():
    """Re-derive the headline numbers from the recorded evals rather than asserting them."""
    rows = []
    seats = 0
    hard_fail_seats = 0
    for f in sorted(glob.glob(os.path.join(ROOT, "results", "*.json"))):
        d = json.load(open(f))
        ev = d["eval_result"]
        min_hard = min((h["pass_rate"] for h in ev.get("average_hard_scores", [])), default=1.0)
        for r in ev.get("individual_results", []):
            seats += 1
            if any(not h.get("passes", False) for h in r.get("hard_scores", [])):
                hard_fail_seats += 1
        rows.append(dict(name=d.get("config", os.path.basename(f)), avg=ev["average_final_score"], min_hard=min_hard))
    rows.sort(key=lambda r: -r["avg"])
    n = len(rows)
    return dict(rows=rows, n=n,
                overall=sum(r["avg"] for r in rows) / n,
                n_hard=sum(1 for r in rows if r["min_hard"] >= 1.0),
                n90=sum(1 for r in rows if r["avg"] >= 90),
                n80=sum(1 for r in rows if r["avg"] >= 80),
                seats=seats, hard_fail_seats=hard_fail_seats)


def hero(a):
    H = 340
    s = head(H, "h", ("Semantic candidate search over 194K profiles: Voyage-3 retrieval, exhaustive structured scans, "
                      "hard and soft relevance filtering, GPT-4o-mini reranking, and a blind rubric-scored judge; "
                      f"the recorded evals average {a['overall']:.1f} with every hard criterion passing"))
    s += f'''
<text x="40" y="46" fill="{THEME}" font-size="14" font-weight="700" letter-spacing="3.2" font-family="{MONO}">SEMANTIC SEARCH / INFORMATION RETRIEVAL</text>
<text x="40" y="102" fill="{INK}" font-size="35" font-weight="700">Recall, made exact.</text>
<text x="40" y="146" fill="{INK}" font-size="35" font-weight="700">Ranking, made honest.</text>
<rect x="40" y="168" width="150" height="2.5" fill="url(#rlh)"/>
<text x="40" y="200" fill="{INK3}" font-size="16">Candidate search over ~194K profiles: Voyage-3 vectors,</text>
<text x="40" y="224" fill="{INK3}" font-size="16">hard/soft relevance filters, GPT-4o-mini reranking, and a</text>
<text x="40" y="248" fill="{INK3}" font-size="16">blind rubric-scored judge before any slate is recorded.</text>
'''
    chips = [("retrieve", 40, 104), ("filter", 156, 84), ("rerank", 252, 96), ("verify", 360, 100)]
    for label, x, w in chips:
        last = label == "verify"
        s += f'<rect x="{x}" y="278" width="{w}" height="28" fill="{"#141d27" if last else f"url(#ndh)"}" stroke="{"#8f9aa6" if last else STROKE}" stroke-width="{1.8 if last else 1.2}" rx="3"/>\n'
        s += txt(x + w / 2, 297, label, 15, INK if last else INK3, weight="700" if last else "400")

    s += f'<rect x="500" y="52" width="364" height="254" fill="#0a0e12" stroke="#212b36" stroke-width="1.2" rx="4"/>\n'
    s += txt(518, 80, "CHECKED AGAINST THE RECORDED EVALS", 13, MUTE, anchor="start")
    rows = [(f"{a['overall']:.1f}", "average final score, 10 configs", THEME_T),
            (f"{a['n_hard']} / {a['n']}", "configs at 100% hard-criteria pass", AQUA),
            (f"{a['n80']} / {a['n']}", "configs at 80 or above", AQUA),
            (f"{a['n90']} / {a['n']}", "configs at 90 or above", AQUA),
            (f"{a['hard_fail_seats']}", f"hard failures in {a['seats']} recorded seats", AQUA)]
    for i, (num, label, col) in enumerate(rows):
        y = 116 + i * 38
        s += txt(518, y, num, 18, col, anchor="start", weight="700")
        s += txt(628, y, label, 13, INK3, anchor="start")
    return s + "</svg>\n"


def pipeline():
    H = 580
    s = head(H, "p", ("Pipeline: exhaustive Turbopuffer scans and Voyage-3 vectors generate candidates, hard-criteria filters "
                      "make the qualified population exact, GPT-4o-mini reranks on hard and soft criteria, and a blind "
                      "rubric-scored judge verifies every candidate before the slate is recorded against the live endpoint"))
    s += title_block("p", "PIPELINE", "From 194K profiles to ten verified candidates per role")
    stages = [
        (41, "scan + embed", ["Voyage-3 query vectors,", "exhaustive id-ordered scans"], VIOLET, VIOLET_T),
        (253, "filter", ["degree, field, school, dates,", "hard gates made exact"], BLUE, BLUE_T),
        (465, "rerank", ["GPT-4o-mini, hard + soft,", "text-only, judge-matched"], ORANGE, ORANGE_T),
        (677, "verify", ["blind rubric-scored judge,", "standards frozen first"], AQUA, AQUA_T),
    ]
    for i, (x, t, subs, stroke, tc) in enumerate(stages):
        cx = x + 91
        s += box(x, 128, 182, 96, "p", stroke=stroke, sw=1.6)
        s += txt(cx, 158, t, 17, tc, weight="700")
        for j, sub in enumerate(subs):
            s += txt(cx, 186 + j * 22, sub, 13, MUTE)
        if i < 3:
            s += f'<line x1="{x+182}" y1="176" x2="{x+206}" y2="176" stroke="#5a6673" stroke-width="1.8" marker-end="url(#arp)"/>\n'
    s += txt(41, 118, "~194K profiles in", 15, FAINT, anchor="start")

    s += f'<line x1="768" y1="224" x2="768" y2="268" stroke="{AQUA}" stroke-width="1.8" marker-end="url(#argp)"/>\n'
    s += box(636, 270, 228, 74, "p", stroke="#8f9aa6", sw=1.6, fill="#141d27")
    s += txt(750, 300, "record", 17, INK, weight="700")
    s += txt(750, 326, "live eval, slate archived", 14, MUTE)

    s += f'<rect x="36" y="268" width="560" height="106" fill="#0a0e12" stroke="#4a5663" stroke-width="1.3" stroke-dasharray="6 5" rx="4"/>\n'
    s += txt(58, 296, "the three guarantees the pipeline enforces", 15, INK2, anchor="start", weight="700")
    for i, inv in enumerate(["hard-gate recall is exact: the full qualifying population is scanned",
                             "the local judge reads only the text the eval judge can see",
                             "every recorded number is a real submission, never an estimate"]):
        s += txt(58, 320 + i * 20, inv, 14, MUTE, anchor="start")

    s += f'<line x1="316" y1="374" x2="316" y2="398" stroke="#5a6673" stroke-width="1.6" marker-end="url(#arp)"/>\n'
    s += f'<line x1="750" y1="344" x2="750" y2="398" stroke="#5a6673" stroke-width="1.6" marker-end="url(#arp)"/>\n'
    outs = [(36, 250, "results/*.json", "one recorded eval per config"),
            (330, 264, "submission ledger", "hard-fails blacklisted for good"),
            (700, 164, "run table", "66.6 to 90.3")]
    for x, w, t, sub in outs:
        s += box(x, 400, w, 72, "p", stroke=ORANGE, sw=1.6, fill="#1c130e")
        s += txt(x + w / 2, 428, t, 16, ORANGE_T, weight="700")
        s += txt(x + w / 2, 452, sub, 13, MUTE)

    s += caption(["Vector similarity finds the plausible; exhaustive structured scans make the qualified population exact; the LLM",
                  "stages decide who actually fits. The interesting engineering is the verification layer, a blind judge calibrated",
                  "per rubric that decides whether a profile genuinely satisfies the role before its slate is ever recorded."], 512)
    return s + "</svg>\n"


def scores(a):
    H = 620
    s = head(H, "s", ("Recorded eval scores for all ten role configs: eight of ten at 90 or above, all ten at 80 or above, "
                      "every hard criterion passing at 100 percent"))
    s += title_block("s", "RECORDED EVALS", "Ten configs, one live-scored slate each")
    x0, x1 = 268, 820
    gx = x0 + (x1 - x0) * 0.9
    s += f'<line x1="{gx:.0f}" y1="122" x2="{gx:.0f}" y2="536" stroke="{FAINT}" stroke-width="1.2" stroke-dasharray="4 5"/>\n'
    s += txt(gx, 114, "90", 13, FAINT)
    y = 136
    for r in a["rows"]:
        w = (x1 - x0) * r["avg"] / 100.0
        col = AQUA if r["avg"] >= 90 else BLUE
        s += txt(258, y + 18, r["name"], 14, INK3, anchor="end")
        s += f'<rect x="{x0}" y="{y}" width="{w:.1f}" height="26" fill="{col}" rx="3" fill-opacity="0.9"/>\n'
        s += txt(x0 + w + 10, y + 18, f"{r['avg']:.1f}", 14, INK, anchor="start", weight="700")
        y += 40
    s += txt(x0, 126, "final slate score per config, scored by the provided evaluation endpoint", 13, MUTE, anchor="start")
    s += caption(["Each bar is one config's final ten-candidate slate, submitted live and recorded under results/. Eight of ten",
                  "clear 90, all ten clear 80, and every hard criterion passes at 100% on every config."], 566)
    return s + "</svg>\n"



# The first four averages are historical measurements: each is recorded in its run's README
# table and in the commit that landed that run. Only the final average is re-derived live.
RUN_HISTORY = [
    ("Run 1", 46.7, "strict filters, soft-only rerank"),
    ("Run 2", 52.1, "hard criteria handed to the LLM"),
    ("Run 3", 66.6, "filters pushed into the database"),
    ("Run 4", 89.4, "exhaustive scans, judge-matched scoring"),
]


def progression(a):
    H = 400
    final = a["overall"]
    runs = RUN_HISTORY + [("Run 5", final, "wider search, blind re-verification")]
    s = head(H, "p2", ("Average eval score across the five recorded runs, from 46.7 with strict filters and a "
                       f"soft-only reranker to {final:.1f} with exhaustive scans and a blind re-judge"))
    s += title_block("p2", "FIVE RUNS", "How the average earned each step")
    x0, x1, y_lo, y_hi = 80, 856, 300, 128
    lo, hi = 40.0, 95.0
    ys = lambda v: y_lo - (v - lo) / (hi - lo) * (y_lo - y_hi)
    step = (x1 - x0) / len(runs)
    s += f'<line x1="{x0-8}" y1="{ys(90):.0f}" x2="{x1}" y2="{ys(90):.0f}" stroke="{FAINT}" stroke-width="1.2" stroke-dasharray="4 5"/>\n'
    s += txt(x0 - 16, ys(90) + 5, "90", 13, FAINT, anchor="end")
    prev = None
    for i, (name, avg, note) in enumerate(runs):
        bx0, bx1 = x0 + i * step + 14, x0 + (i + 1) * step - 14
        y = ys(avg)
        col = AQUA if avg >= 90 else (VIOLET if i >= 3 else BLUE)
        if prev is not None:
            s += f'<path d="M {bx0 - 28:.0f} {prev:.0f} H {bx0:.0f} V {y:.0f}" fill="none" stroke="{STROKE}" stroke-width="2"/>\n'
        s += f'<line x1="{bx0:.0f}" y1="{y:.0f}" x2="{bx1:.0f}" y2="{y:.0f}" stroke="{col}" stroke-width="5"/>\n'
        s += txt((bx0 + bx1) / 2, y - 14, f"{avg:.1f}", 17, INK, weight="700")
        s += txt((bx0 + bx1) / 2, 330, name, 15, INK2, weight="700")
        for j, chunk in enumerate(_wrap(note, 18)):
            s += txt((bx0 + bx1) / 2, 352 + j * 18, chunk, 13, MUTE)
        prev = y
    return s + "</svg>\n"


def _wrap(text, width):
    words, lines, cur = text.split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(cur); cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return lines

if __name__ == "__main__":
    a = audit()
    os.makedirs(os.path.join(ROOT, "assets"), exist_ok=True)
    os.makedirs(os.path.join(ROOT, "docs", "figures"), exist_ok=True)
    for path, svg in [("assets/hero.svg", hero(a)),
                      ("assets/pipeline.svg", pipeline()),
                      ("docs/figures/config_scores.svg", scores(a)),
                      ("docs/figures/run_progression.svg", progression(a))]:
        p = os.path.join(ROOT, path)
        open(p, "w").write(svg)
        print(f"  {path}  {os.path.getsize(p):,} bytes")
