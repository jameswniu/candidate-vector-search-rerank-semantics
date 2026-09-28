"""Colours, font stacks and SVG definitions shared by the four figures that docs/generate_visuals.py draws.

The figures sit on a dark gradient canvas under a faint dot grid. Text runs through five greys, INK down to
FAINT, and four accents mark stages and results, each with a lighter _T shade for text. Contrast on the
lightest canvas stop: INK 16.7:1, INK2 11.8:1, INK3 7.3:1, MUTE 5.0:1, FAINT 3.1:1, VIOLET_T 6.6:1, AQUA 5.3:1.
"""

SANS = "ui-sans-serif, -apple-system, BlinkMacSystemFont, Segoe UI, Helvetica, Arial, sans-serif"
MONO = "ui-monospace, SFMono-Regular, Menlo, monospace"

BG0, BG1, BG2 = "#12161c", "#0c1013", "#080a0d"  # canvas gradient, top left to bottom right; BG1 also backs halos
DOT = "#161d26"  # dot grid over the canvas
NODE_A, NODE_B = "#19212b", "#111820"  # stage box fill, top to bottom
PANEL, PANEL_EDGE = "#0a0e12", "#212b36"  # hero panels, their edges and dividers
RECORD, RECORD_EDGE = "#141d27", "#8f9aa6"  # the Submit stage, which records the run
OUTPUT = "#1c130e"  # the three output boxes, edged in ORANGE
GRID, STROKE, ARROW = "#1e2731", "#3a4552", "#5a6673"  # chart gridlines, the line through the runs, flow arrows
VIOLET, BLUE, ORANGE, AQUA = "#8a63d2", "#3987e5", "#d95926", "#199e70"  # edges, bars, points and pass counts
VIOLET_T, BLUE_T, ORANGE_T, AQUA_T = "#ab8ce6", "#6fa8ec", "#e0763f", "#35b183"  # the same accents, for text
INK, INK2, INK3 = "#f3f6f9", "#c8d2dc", "#9aa5b1"  # titles and values, run names, subtitles and labels
MUTE, FAINT = "#7d8896", "#5c6773"  # captions and descriptions, axis numbers and the 90 line


def backdrop(uid, w, h):
    """The <defs> a figure uses, then its canvas: the gradient with the dot grid over it.

    Defines the canvas gradient bg<uid>, the dot grid dot<uid> (dots every 36 units), the stage box
    gradient nd<uid>, and two arrowheads, ah<uid> in ARROW and ahg<uid> in AQUA.
    """
    heads = "".join(f'<marker id="{mid}{uid}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" '
                    f'orient="auto"><path d="M 0 0 L 10 5 L 0 10 z" fill="{col}"/></marker>\n'
                    for mid, col in (("ah", ARROW), ("ahg", AQUA)))
    return (f'<defs>\n<linearGradient id="bg{uid}" x1="0" y1="0" x2="0.75" y2="1"><stop offset="0" stop-color="{BG0}"/>'
            f'<stop offset="0.55" stop-color="{BG1}"/><stop offset="1" stop-color="{BG2}"/></linearGradient>\n'
            f'<pattern id="dot{uid}" width="36" height="36" patternUnits="userSpaceOnUse">'
            f'<circle cx="1.3" cy="1.3" r="0.95" fill="{DOT}"/></pattern>\n'
            f'<linearGradient id="nd{uid}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{NODE_A}"/>'
            f'<stop offset="1" stop-color="{NODE_B}"/></linearGradient>\n'
            f'{heads}</defs>\n'
            f'<rect width="{w}" height="{h}" fill="url(#bg{uid})"/>\n'
            f'<rect width="{w}" height="{h}" fill="url(#dot{uid})"/>\n')
