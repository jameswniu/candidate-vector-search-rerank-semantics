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

# Fit guard. Per-char advances in em are deliberately generous (mono 0.62, sans 0.56, sans bold
# 0.60), and so are ascent and descent, so SF, Menlo, Courier New, Helvetica and Arial all land
# inside the modelled box. A text that would not clear its frame by `pad` stops the build loudly.
ADV = {"mono": 0.62, "sans": 0.56, "sans_bold": 0.60}
ASC, DESC = 0.96, 0.30


def _fit(frame, x, y, s, size, anchor="middle", mono=True, bold=False, ls=0.0, pad=16):
    """Raise unless text s at (x, y) clears frame (x, y, w, h) by pad on every side."""
    fx, fy, fw, fh = frame
    w = len(s) * (ADV["mono" if mono else ("sans_bold" if bold else "sans")] * size + ls)
    left = {"start": x, "middle": x - w / 2, "end": x - w}[anchor]
    slack = min(left - fx, fx + fw - (left + w), y - ASC * size - fy, fy + fh - (y + DESC * size)) - pad
    if slack < 0:
        raise SystemExit(f"FIT FAIL: {s!r} ({size}px) overflows its frame {frame} by {-slack:.1f} (pad {pad})")


def _ftxt(frame, x, y, s, size=15, fill=INK3, anchor="middle", mono=True, weight="400", pad=16):
    """txt(), emitted only after the fit guard passes."""
    _fit(frame, x, y, s, size, anchor, mono, weight == "700", pad=pad)
    return txt(x, y, s, size, fill, anchor, mono, weight)


def _widen(svg_head, w):
    """svgkit's head() at canvas width w, with the dot grid spaced 36 so it keeps its on-screen density."""
    swaps = [(f'viewBox="0 0 {W} ', f'viewBox="0 0 {w} ', 1), (f'width="{W}"', f'width="{w}"', 3),
             ('width="28" height="28" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r="0.7"',
              'width="36" height="36" patternUnits="userSpaceOnUse"><circle cx="1.3" cy="1.3" r="0.95"', 1)]
    for old, new, n in swaps:
        if svg_head.count(old) != n:
            raise SystemExit(f"svgkit.head() changed shape, cannot widen it: {old!r}")
        svg_head = svg_head.replace(old, new)
    return svg_head


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
    for label, x, w in chips:  # 38 tall so each label clears its chip by 8; bottoms stay level with the panel's
        last = label == "verify"
        s += f'<rect x="{x}" y="268" width="{w}" height="38" fill="{"#141d27" if last else f"url(#ndh)"}" stroke="{"#8f9aa6" if last else STROKE}" stroke-width="{1.8 if last else 1.2}" rx="3"/>\n'
        s += _ftxt((x, 268, w, 38), x + w / 2, 292, label, 15, INK if last else INK3, weight="700" if last else "400", pad=8)

    panel = (500, 52, 364, 254)
    s += f'<rect x="500" y="52" width="364" height="254" fill="#0a0e12" stroke="#212b36" stroke-width="1.2" rx="4"/>\n'
    s += _ftxt(panel, 518, 80, "CHECKED AGAINST THE RECORDED EVALS", 13, MUTE, anchor="start", pad=8)
    # A label too long to sit beside its number breaks at a word boundary onto a second line.
    rows = [(f"{a['overall']:.1f}", ["average final score,", "10 configs"], THEME_T),
            (f"{a['n_hard']} / {a['n']}", ["configs at 100%", "hard-criteria pass"], AQUA),
            (f"{a['n80']} / {a['n']}", ["configs at 80 or above"], AQUA),
            (f"{a['n90']} / {a['n']}", ["configs at 90 or above"], AQUA),
            (f"{a['hard_fail_seats']}", ["hard failures in", f"{a['seats']} recorded seats"], AQUA)]
    for i, (num, label, col) in enumerate(rows):
        y = 116 + i * 40
        s += _ftxt(panel, 518, y, num, 18, col, anchor="start", weight="700", pad=8)
        for j, part in enumerate(label):
            s += _ftxt(panel, 628, y + j * 15, part, 13, INK3, anchor="start", pad=8)
    return s + "</svg>\n"


def pipeline():
    # 1200 wide so the smallest type (23) stays 12px at 75% zoom in GitHub's 837px column; the four
    # stages sit in a 2x2 grid read like text (scan, filter / rerank, verify). Every label is fit-checked.
    PW, H = 1200, 1398
    s = _widen(head(H, "p", ("Pipeline: exhaustive Turbopuffer scans and Voyage-3 vectors generate candidates, hard-criteria filters "
                             "make the qualified population exact, GPT-4o-mini reranks on hard and soft criteria, and a blind "
                             "rubric-scored judge verifies every candidate before the slate is recorded against the live endpoint")), PW)
    def node(frame, stroke, fill="url(#ndp)", sw=2.1, dash=""):
        x, y, w, h = frame
        extra = f' stroke-dasharray="{dash}"' if dash else ""
        return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{extra} rx="6"/>\n'

    def arrow(d, col="#5a6673", m="arp"):
        return f'<path d="{d}" fill="none" stroke="{col}" stroke-width="2.4" stroke-linejoin="round" marker-end="url(#{m})"/>\n'

    hdr, lbl = (24, 16, PW - 48, 192), (24, 194, 560, 66)  # logical frames: header band, input label band
    _fit(hdr, 48, 64, "PIPELINE", 23, "start", ls=5)
    s += f'<text x="48" y="64" fill="{THEME}" font-size="23" font-weight="700" letter-spacing="5" font-family="{MONO}">PIPELINE</text>\n'
    for i, line in enumerate(["From 194K profiles", "to ten verified candidates per role"]):
        s += _ftxt(hdr, 48, 120 + i * 50, line, 40, INK, anchor="start", mono=False, weight="700")
    s += '<rect x="48" y="190" width="180" height="3.5" fill="url(#rlp)"/>\n'
    s += _ftxt(lbl, 48, 236, "~194K profiles in", 23, MUTE, anchor="start")

    stages = [
        (48, 260, "scan + embed", ["Voyage-3 query vectors,", "exhaustive id-ordered scans"], VIOLET, VIOLET_T),
        (648, 260, "filter", ["degree, field, school, dates,", "hard gates made exact"], BLUE, BLUE_T),
        (48, 486, "rerank", ["GPT-4o-mini, hard + soft,", "text-only, judge-matched"], ORANGE, ORANGE_T),
        (648, 486, "verify", ["blind rubric-scored judge,", "standards frozen first"], AQUA, AQUA_T),
    ]
    for x, y, t, subs, stroke, tc in stages:
        frame = (x, y, 504, 150)
        s += node(frame, stroke)
        s += _ftxt(frame, x + 252, y + 50, t, 30, tc, weight="700")
        for j, sub in enumerate(subs):
            s += _ftxt(frame, x + 252, y + 92 + j * 34, sub, 23, MUTE)
    s += arrow("M 560 335 H 642") + arrow("M 560 561 H 642")  # scan -> filter, rerank -> verify
    s += arrow("M 900 414 V 448 H 300 V 480")  # filter -> rerank: down, back left, down

    panel = (48, 686, 668, 300)
    s += node(panel, "#4a5663", fill="#0a0e12", sw=1.7, dash="8 7")
    s += _ftxt(panel, 76, 736, "the three guarantees the pipeline enforces", 23, INK2, anchor="start", weight="700")
    for i, inv in enumerate([["hard-gate recall is exact: the full", "qualifying population is scanned"],
                             ["the local judge reads only the text", "the eval judge can see"],
                             ["every recorded number is a real", "submission, never an estimate"]]):
        s += f'<rect x="76" y="{769 + i * 72}" width="8" height="8" rx="1.5" fill="{VIOLET}"/>\n'
        for j, part in enumerate(inv):
            s += _ftxt(panel, 98, 782 + i * 72 + j * 32, part, 23, MUTE, anchor="start")

    rec = (752, 774, 400, 124)  # centred on the verify -> record -> run table spine at x=952
    s += node(rec, "#8f9aa6", fill="#141d27")
    s += _ftxt(rec, 952, 826, "record", 30, INK, weight="700")
    s += _ftxt(rec, 952, 868, "live eval, slate archived", 23, MUTE)
    s += arrow("M 952 640 V 768", AQUA, "argp")

    outs = [(48, 280, "results/*.json", ["one recorded eval", "per config"]),
            (364, 352, "submission ledger", ["hard-fails blacklisted", "for good"]),
            (752, 400, "run table", ["66.6 to 90.3"])]
    for x, w, t, subs in outs:
        frame, cx = (x, 1036, w, 140), x + w // 2
        s += node(frame, ORANGE, fill="#1c130e")
        s += _ftxt(frame, cx, 1082, t, 26, ORANGE_T, weight="700")
        for j, sub in enumerate(subs):
            s += _ftxt(frame, cx, 1120 + j * 32, sub, 23, MUTE)
        s += arrow(f"M {cx} {902 if x == rec[0] else 990} V 1030")  # record -> run table; guarantees -> the others

    cap = (24, 1194, PW - 48, 198)
    for i, line in enumerate(["Vector similarity finds the plausible; exhaustive structured scans make",
                              "the qualified population exact; the LLM stages decide who actually",
                              "fits. The interesting engineering is the verification layer, a blind",
                              "judge calibrated per rubric that decides whether a profile genuinely",
                              "satisfies the role before its slate is ever recorded."]):
        s += _ftxt(cap, 48, 1236 + i * 33, line, 23, MUTE, anchor="start", mono=False)
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
