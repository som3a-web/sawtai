#!/usr/bin/env python3
"""Executive-briefing diagrams for SawtAI.

Layout uses a top-down coordinate system (y grows downward, like CSS) to keep
placement arithmetic honest. Sheet.Y() converts to matplotlib coordinates.
"""

import os
import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Circle, Rectangle, Polygon
from matplotlib.lines import Line2D

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "img")
os.makedirs(OUT, exist_ok=True)

TEAL       = "#0d5c63"
TEAL_MID   = "#14848c"
TEAL_PALE  = "#e4f0f0"
AMBER      = "#b8690b"
AMBER_PALE = "#fdf1de"
RED        = "#a8322a"
RED_PALE   = "#fbeae8"
GREEN      = "#1f7a44"
GREEN_PALE = "#e7f4ec"
INK        = "#1f2937"
GREY       = "#64748b"
GREY_PALE  = "#f1f5f9"
LINE       = "#cbd5e1"

for fam in ("Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"):
    if fam in {f.name for f in matplotlib.font_manager.fontManager.ttflist}:
        plt.rcParams["font.family"] = fam
        break
plt.rcParams["font.size"] = 11


class Sheet:
    """A drawing surface 100 units wide, with y measured downward from the top."""

    def __init__(self, w_in, h_in):
        self.W = 100.0
        self.H = 100.0 * h_in / w_in
        self.fig, self.ax = plt.subplots(figsize=(w_in, h_in))
        self.ax.set_xlim(0, self.W)
        self.ax.set_ylim(0, self.H)
        self.ax.axis("off")
        self.ax.invert_yaxis()          # y grows downward
        self.fig.patch.set_facecolor("white")

    # ---- primitives ----
    def box(self, x, y, w, h, text="", fill="white", edge=LINE, tc=INK,
            fs=11, bold=False, wrap=None, lw=1.4, r=1.6, va="center"):
        self.ax.add_patch(FancyBboxPatch(
            (x, y), w, h, boxstyle=f"round,pad=0,rounding_size={r}",
            facecolor=fill, edgecolor=edge, linewidth=lw, zorder=2,
            mutation_aspect=1))
        if text:
            t = textwrap.fill(text, wrap) if wrap else text
            ty = y + h / 2 if va == "center" else y + 1.8
            self.ax.text(x + w / 2, ty, t, ha="center",
                         va="center" if va == "center" else "top",
                         fontsize=fs, color=tc, zorder=4,
                         fontweight="bold" if bold else "normal",
                         linespacing=1.5)
        return (x + w / 2, y + h / 2)

    def text(self, x, y, s, fs=11, color=INK, bold=False, ha="center",
             va="center", wrap=None, italic=False):
        t = textwrap.fill(s, wrap) if wrap else s
        self.ax.text(x, y, t, ha=ha, va=va, fontsize=fs, color=color, zorder=5,
                     fontweight="bold" if bold else "normal",
                     fontstyle="italic" if italic else "normal",
                     linespacing=1.5)

    def arrow(self, p1, p2, color=GREY, lw=1.8, rad=0.0, ls="-"):
        self.ax.add_patch(FancyArrowPatch(
            p1, p2, arrowstyle="-|>", mutation_scale=14, linewidth=lw,
            color=color, zorder=3, linestyle=ls,
            connectionstyle=f"arc3,rad={rad}", shrinkA=1.5, shrinkB=1.5))

    def tick(self, cx, cy, color="white", s=1.0):
        """Vector check mark (font glyph is unavailable)."""
        pts = [(cx - 0.75 * s, cy), (cx - 0.2 * s, cy + 0.6 * s),
               (cx + 0.85 * s, cy - 0.7 * s)]
        self.ax.add_line(Line2D([p[0] for p in pts], [p[1] for p in pts],
                                color=color, lw=2.2 * s, zorder=6,
                                solid_capstyle="round",
                                solid_joinstyle="round"))

    def cross(self, cx, cy, color=RED, s=1.0):
        for dx in (1, -1):
            self.ax.add_line(Line2D([cx - 0.8 * s * dx, cx + 0.8 * s * dx],
                                    [cy - 0.8 * s, cy + 0.8 * s],
                                    color=color, lw=2.4 * s, zorder=6,
                                    solid_capstyle="round"))

    def triangle_up(self, cx, cy, color=INK, s=1.0):
        self.ax.add_patch(Polygon(
            [(cx, cy - 0.9 * s), (cx - 0.85 * s, cy + 0.6 * s),
             (cx + 0.85 * s, cy + 0.6 * s)],
            closed=True, facecolor=color, edgecolor="none", zorder=6))

    def save(self, name):
        self.fig.savefig(os.path.join(OUT, name), dpi=200, bbox_inches="tight",
                         pad_inches=0.30, facecolor="white")
        plt.close(self.fig)
        print("wrote", name)


# ============================================================ 1. the problem
def d1_problem():
    s = Sheet(11, 5.6)

    s.text(10, 3.0, "WHAT ARRIVES", fs=9.5, color=GREY, bold=True)
    ch = ["Social media posts", "Complaint forms", "Emails",
          "Survey responses", "Call centre notes"]
    top, bh, gap = 7.0, 5.6, 1.5
    for i, c in enumerate(ch):
        y = top + i * (bh + gap)
        s.box(1, y, 18, bh, c, fill=GREY_PALE, edge=LINE, fs=9.5)
        s.arrow((19.4, y + bh / 2), (26.8, 24), color=LINE, lw=1.1)
    s.text(10, top + 4 * (bh + gap) + bh + 3.2, "thousands every week",
           fs=9.5, color=GREY, italic=True)

    s.box(27, 14, 21, 20,
          "A small team reads\nwhat it can get to",
          fill="white", edge=AMBER, fs=10.5, lw=1.8)
    s.text(37.5, 27.5, "in Arabic, dialect and English,\noften mixed together",
           fs=9, color=GREY)
    s.text(37.5, 37, "they see perhaps 5–10% of it", fs=9.5, color=AMBER,
           bold=True)

    s.arrow((48.4, 20), (54.5, 17), color=GREY, rad=-0.1)
    s.arrow((48.4, 28), (54.5, 32), color=RED, rad=0.1)

    s.box(55, 12, 22, 10, "A weekly summary", fill=GREY_PALE, edge=LINE, fs=10.5)
    s.box(55, 27, 22, 10, "Problems noticed\nonly once they trend",
          fill=RED_PALE, edge=RED, tc=RED, fs=10, bold=True)

    s.arrow((77.4, 32), (83.5, 32), color=RED, lw=2.0)
    s.box(84, 25, 15, 14, "By then\nit is already\npublic",
          fill=RED, edge=RED, tc="white", fs=11, bold=True)

    s.text(50, 48.0,
           "The entity is always answering yesterday — and only the part of it somebody happened to read.",
           fs=11, color=INK, italic=True)
    s.save("01-problem.png")


# =========================================================== 2. big picture
def d2_bigpicture():
    s = Sheet(11, 6.2)

    s.text(9.5, 3.0, "IN", fs=10, color=GREY, bold=True)
    srcs = ["Social media", "Complaints", "Emails", "Surveys", "Call centre"]
    top, bh, gap = 8.0, 5.4, 2.4
    for i, c in enumerate(srcs):
        y = top + i * (bh + gap)
        s.box(1, y, 16, bh, c, fill=GREY_PALE, fs=9.5)
        s.arrow((17.4, y + bh / 2), (26.5, 29.5), color=LINE, lw=1.1)

    # platform
    s.box(27, 6, 32, 47, "", fill=TEAL_PALE, edge=TEAL, lw=2.2, r=2.4)
    s.text(43, 12.5, "SawtAI", fs=18, color=TEAL, bold=True)
    s.text(43, 17.5, "one platform, three jobs", fs=9.5, color=TEAL_MID,
           italic=True)

    pil = [("1.  Understand", "reads everything, in Arabic\nand English"),
           ("2.  Draft", "writes the official reply, from\napproved sources only"),
           ("3.  Warn", "flags an issue before it\nbecomes a crisis")]
    py, ph, pg = 21.5, 9.2, 1.8
    for i, (t, sub) in enumerate(pil):
        y = py + i * (ph + pg)
        s.box(30, y, 26, ph, "", fill="white", edge=TEAL_MID, lw=1.3)
        s.text(32, y + 3.0, t, fs=11, color=TEAL, bold=True, ha="left")
        s.text(32, y + 6.4, sub, fs=8.6, color=GREY, ha="left")

    s.arrow((59.4, 29.5), (66.5, 29.5), color=TEAL, lw=2.4)

    s.text(82.5, 3.0, "OUT", fs=10, color=GREY, bold=True)
    s.box(67, 8, 32, 14,
          "A communication officer\nwho can see all of it\nand act on the right thing",
          fill="white", edge=TEAL, fs=10.5, lw=1.6)
    s.arrow((83, 22.4), (83, 27.6), color=TEAL, lw=1.8)
    s.box(67, 28, 32, 14, "An approved reply,\nstatement or alert",
          fill=GREEN_PALE, edge=GREEN, tc=GREEN, fs=11, bold=True, lw=1.6)
    s.text(83, 45.5, "a named person approves\nevery single one",
           fs=9.5, color=GREEN, bold=True)

    s.text(50, 55.5,
           "Nothing reaches the public without a named person approving it.",
           fs=11.5, color=INK, bold=True)
    s.save("02-bigpicture.png")


# ============================================================= 3. three jobs
def d3_pillars():
    s = Sheet(11, 4.9)
    cards = [
        (TEAL, TEAL_PALE, "1", "Understand the public",
         "Every message is read — not a sample.",
         "It handles Modern Standard Arabic, Gulf dialect, English, and the "
         "mixture of all three that people actually write in.",
         "We know what people are unhappy about today, not last month."),
        (AMBER, AMBER_PALE, "2", "Draft the response",
         "It writes the official reply for the officer.",
         "It may only use the entity's own approved documents, and it shows "
         "which paragraph every sentence came from.",
         "Consistent, on-message replies in minutes instead of hours."),
        (GREEN, GREEN_PALE, "3", "Warn before the crisis",
         "It watches how fast an issue is growing.",
         "When the pattern matches an issue about to escalate, it alerts the "
         "team and suggests the response plan.",
         "Hours or days of warning, instead of finding out from the news."),
    ]
    w, gap = 31.5, 2.0
    for i, (c, pale, num, head, l1, l2, l3) in enumerate(cards):
        x = 1.0 + i * (w + gap)
        s.box(x, 2, w, s.H - 4, "", fill="white", edge=c, lw=1.8, r=2.0)
        s.ax.add_patch(Rectangle((x, 2), w, 10, facecolor=pale,
                                 edgecolor="none", zorder=3))
        s.ax.add_patch(Circle((x + 5.0, 7.0), 2.7, facecolor=c,
                              edgecolor="none", zorder=4))
        s.text(x + 5.0, 7.0, num, fs=13.5, color="white", bold=True)
        s.text(x + 9.6, 7.0, head, fs=12, color=c, bold=True, ha="left")

        s.text(x + 2.4, 15.5, l1, fs=10.3, color=INK, ha="left", va="top",
               wrap=34, bold=True)
        s.text(x + 2.4, 22.5, l2, fs=9.4, color=GREY, ha="left", va="top",
               wrap=38)

        s.ax.add_line(Line2D([x + 2.4, x + w - 2.4], [33.5, 33.5],
                             color=LINE, lw=1, zorder=4))
        s.text(x + 2.4, 36.0, "WHAT IT MEANS FOR US", fs=7.5, color=c,
               ha="left", va="top", bold=True)
        s.text(x + 2.4, 39.0, l3, fs=9.6, color=INK, ha="left", va="top",
               wrap=38)
    s.save("03-pillars.png")


# ==================================================== 4. one complaint's path
def d4_journey():
    s = Sheet(11, 4.6)
    steps = [
        ("07:14", "A resident posts\na complaint", GREY_PALE, GREY, INK, False),
        ("07:14", "Personal details\nstripped out\nautomatically", RED_PALE, RED, RED, True),
        ("07:15", "Understood, sorted,\nsent to the right\ndepartment", TEAL_PALE, TEAL, TEAL, False),
        ("07:18", "Officer asks for\na draft reply", TEAL_PALE, TEAL, TEAL, False),
        ("07:19", "Draft written, with\nthe source of every\nsentence shown", AMBER_PALE, AMBER, AMBER, False),
        ("07:22", "Manager reads it,\nedits and approves", GREEN_PALE, GREEN, GREEN, True),
        ("07:23", "Reply published", GREEN, GREEN, "white", True),
    ]
    n, w, gap, x0 = len(steps), 12.4, 1.6, 1.0
    rail = 13.5
    s.ax.add_line(Line2D([x0 + w / 2, x0 + (n - 1) * (w + gap) + w / 2],
                         [rail, rail], color=LINE, lw=2, zorder=1))
    for i, (t, txt, fill, edge, tc, bold) in enumerate(steps):
        x = x0 + i * (w + gap)
        s.text(x + w / 2, 5.5, t, fs=11.5, color=TEAL, bold=True)
        s.ax.add_patch(Circle((x + w / 2, rail), 1.5, facecolor=edge,
                              edgecolor="white", linewidth=2, zorder=4))
        s.box(x, 18, w, 15.5, txt, fill=fill, edge=edge, tc=tc, fs=8.7,
              bold=bold, lw=1.5)
        if i < n - 1:
            s.arrow((x + w + 0.2, rail), (x + w + gap - 0.2, rail),
                    color=LINE, lw=1.4)

    s.box(1.0, 37, 44, 8.5, "Today this takes one to two working days.",
          fill="white", edge=LINE, tc=GREY, fs=11)
    s.box(47, 37, 52, 8.5,
          "The officer still writes and decides.\nThe system removes the waiting.",
          fill=TEAL_PALE, edge=TEAL, tc=TEAL, fs=10.5, bold=True)
    s.save("04-journey.png")


# ================================================= 5. why it cannot invent
def d5_safety():
    s = Sheet(11, 5.9)

    # ---- top row ----
    s.box(4, 3, 21, 10, "An officer asks\nfor a reply",
          fill=GREY_PALE, edge=GREY, fs=10.5)
    s.arrow((25.4, 8), (30.5, 8), color=GREY)
    s.box(31, 3, 26, 10,
          "The system searches\nONLY the entity's own\napproved documents",
          fill=TEAL_PALE, edge=TEAL, tc=TEAL, fs=9.7, lw=1.7)
    s.arrow((57.4, 8), (62.5, 8), color=GREY)
    s.box(63, 1.5, 24, 13, "Is there an approved\nsource that\nsupports it?",
          fill="white", edge=AMBER, tc=AMBER, fs=10.2, bold=True, lw=2.1)

    # ---- NO branch (right column) ----
    s.arrow((79, 14.8), (79, 20.5), color=RED, lw=2.2)
    s.text(81.5, 17.5, "NO", fs=11, color=RED, bold=True, ha="left")
    s.box(67, 21, 31, 15,
          "It refuses to write\nanything at all.\n\nIt names the document that\n"
          "would need to exist, and\nasks for it to be added.",
          fill=RED_PALE, edge=RED, tc=RED, fs=9.4, lw=1.9)
    s.text(82.5, 40.5, "This is the most important\nbehaviour in the system.",
           fs=10, color=RED, bold=True)

    # ---- YES branch (three checks across) ----
    s.arrow((64, 13.5), (34, 20.5), color=GREEN, lw=2.2, rad=0.20)
    s.text(50, 20.0, "YES", fs=11, color=GREEN, bold=True)

    checks = [
        "It writes the reply, and marks every sentence with the document and paragraph it came from",
        "A second, separate check re-reads each sentence against its source and flags anything unsupported",
        "A named manager reads it, edits it and approves it — nothing is published without that",
    ]
    cw, cgap = 20.0, 2.0
    for i, t in enumerate(checks):
        x = 2 + i * (cw + cgap)
        s.box(x, 22, cw, 16, "", fill=GREEN_PALE, edge=GREEN, lw=1.5)
        s.text(x + cw / 2, 25.5, f"CHECK {i + 1}", fs=7.8, color=GREEN,
               bold=True)
        s.text(x + cw / 2, 31.5, t, fs=9.0, color=INK, wrap=28)
        if i < 2:
            s.arrow((x + cw + 0.2, 30), (x + cw + cgap - 0.2, 30),
                    color=GREEN, lw=1.8)

    s.arrow((34, 38.3), (34, 41.2), color=GREEN, lw=2.2)
    s.box(2, 41.5, 64, 8.5, "Published",
          fill=GREEN, edge=GREEN, tc="white", fs=13.5, bold=True)
    s.save("05-safety.png")


# ================================================== 6. early-warning timeline
def d6_warning():
    fig, ax = plt.subplots(figsize=(11, 4.7))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    t = np.linspace(0, 10, 400)
    risk = 18 + 72 / (1 + np.exp(-(t - 6.4) * 1.2)) + np.sin(t * 3.1) * 1.6
    ax.plot(t, risk, color=TEAL, lw=3, zorder=6)
    ax.fill_between(t, 0, risk, color=TEAL, alpha=0.07, zorder=1)

    ax.axhline(55, color=AMBER, lw=1.6, ls="--", zorder=3)
    ax.text(0.12, 57.5, "Alert threshold", color=AMBER, fontsize=10,
            fontweight="bold")

    at = t[np.argmax(risk > 55)]
    ax.scatter([at], [55], s=190, color=AMBER, zorder=9, edgecolor="white",
               linewidth=2.5)
    ax.text(at - 0.25, 68, "Alert raised\n11 June, 14:00", fontsize=10.5,
            color=AMBER, fontweight="bold", ha="right", va="center")

    ax.scatter([9.5], [risk[-8]], s=190, color=RED, zorder=9,
               edgecolor="white", linewidth=2.5)
    ax.text(9.42, 99, "The issue peaks publicly\n14 June, 18:00",
            fontsize=10.5, color=RED, fontweight="bold", ha="right",
            va="center")

    ax.annotate("", xy=(at, 20), xytext=(9.5, 20),
                arrowprops=dict(arrowstyle="<->", color=INK, lw=2))
    ax.text((at + 9.5) / 2, 24.5, "76 hours of warning", ha="center",
            fontsize=13.5, fontweight="bold", color=INK)
    ax.text((at + 9.5) / 2, 13.5,
            "time to prepare a statement, brief the department, and respond",
            ha="center", fontsize=9.5, color=GREY, style="italic")

    ax.set_ylim(0, 108)
    ax.set_xlim(0, 10)
    ax.set_ylabel("How risky this issue looks", fontsize=10.5, color=GREY)
    ax.set_xticks([0, 2.5, 5, 7.5, 10])
    ax.set_xticklabels(["10 June", "11 June", "12 June", "13 June", "14 June"],
                       fontsize=10, color=GREY)
    ax.set_yticks([])
    for sp in ("top", "right", "left"):
        ax.spines[sp].set_visible(False)
    ax.spines["bottom"].set_color(LINE)
    ax.set_axisbelow(True)
    fig.savefig(os.path.join(OUT, "06-warning.png"), dpi=200,
                bbox_inches="tight", pad_inches=0.3, facecolor="white")
    plt.close(fig)
    print("wrote 06-warning.png")


# ===================================================== 7. where the data sits
def d7_residency():
    s = Sheet(11, 4.9)

    s.box(1.5, 4, 62, 34, "", fill=TEAL_PALE, edge=TEAL, lw=2.4, r=2.4)
    s.text(32.5, 9.0, "INSIDE GOVERNMENT CONTROL", fs=11.5, color=TEAL,
           bold=True)
    items = ["Every citizen message",
             "The software that reads and understands them",
             "All personal details — removed before anything is stored",
             "Every dashboard, record and audit trail"]
    for i, it in enumerate(items):
        y = 15.5 + i * 5.6
        s.ax.add_patch(Circle((7, y), 1.6, facecolor=TEAL, edgecolor="none",
                              zorder=4))
        s.tick(7, y, color="white", s=0.85)
        s.text(11, y, it, fs=10.3, color=INK, ha="left")

    s.box(67, 4, 31.5, 34, "", fill="white", edge=GREY, lw=1.6, r=2.4)
    s.ax.patches[-1].set_linestyle("--")
    s.text(82.7, 9.0, "OUTSIDE", fs=11.5, color=GREY, bold=True)
    s.box(70, 13.5, 25.5, 12,
          "Only the entity's own\napproved documents,\nand only when writing\na draft",
          fill=AMBER_PALE, edge=AMBER, tc=AMBER, fs=9.5, lw=1.5)
    s.arrow((63.4, 19.5), (69.5, 19.5), color=AMBER, lw=1.9)

    # a second outbound path, explicitly blocked
    s.ax.add_patch(FancyArrowPatch((63.4, 31), (69.5, 31), arrowstyle="-|>",
                                   mutation_scale=14, linewidth=1.9,
                                   color=LINE, zorder=3))
    s.cross(66.4, 31, color=RED, s=1.5)
    s.text(82.7, 31, "No citizen message\never leaves. Not one.",
           fs=9.8, color=RED, bold=True)

    s.text(50, 42.5,
           "There is also a setting where nothing leaves at all — every part runs on our own hardware.",
           fs=10.5, color=INK, italic=True)
    s.save("07-residency.png")


# ============================================================ 8. the plan
def d8_plan():
    fig, ax = plt.subplots(figsize=(11, 4.3))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    rows = [
        ("Week 1   3–9 Aug",    "Data flowing end to end",        0, TEAL),
        ("Week 2   10–16 Aug",  "Dashboard shows real data"   ,   1, TEAL_MID),
        ("Week 3   17–23 Aug",  "Drafting + early warning live",  2, AMBER),
        ("Week 4   24–30 Aug",  "Prove it, film it, submit",      3, GREEN),
    ]
    for i, (lbl, desc, x, c) in enumerate(rows):
        y = len(rows) - 1 - i
        ax.barh(y, 1, left=x, height=0.56, color=c, edgecolor="none", zorder=3)
        ax.text(x + 0.5, y, desc, ha="center", va="center", color="white",
                fontsize=9.6, fontweight="bold", zorder=4)

    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([r[0] for r in reversed(rows)], fontsize=10.5,
                       color=INK)
    ax.set_xticks([0, 1, 2, 3, 4])
    ax.set_xticklabels(["3 Aug", "10 Aug", "17 Aug", "24 Aug", "31 Aug"],
                       fontsize=10, color=GREY)
    ax.set_xlim(-0.04, 4.5)
    ax.set_ylim(-0.85, len(rows) - 0.2)

    ax.axvline(4, color=RED, lw=2.4, zorder=5)
    ax.text(4.09, len(rows) - 0.6, "SUBMISSION\nDEADLINE\n31 August",
            color=RED, fontsize=9.5, fontweight="bold", va="top")

    ax.add_patch(Polygon([(3.0, -0.44), (2.9, -0.58), (3.1, -0.58)],
                         closed=True, facecolor=INK, edgecolor="none",
                         zorder=6, clip_on=False))
    ax.text(3.14, -0.5, "all building stops on Tuesday 25 August",
            color=INK, fontsize=9.5, fontweight="bold", va="center",
            ha="left")

    for sp in ("top", "right", "left"):
        ax.spines[sp].set_visible(False)
    ax.spines["bottom"].set_color(LINE)
    ax.grid(axis="x", color=LINE, lw=0.6, alpha=0.6)
    ax.set_axisbelow(True)
    ax.tick_params(axis="y", length=0)
    fig.savefig(os.path.join(OUT, "08-plan.png"), dpi=200, bbox_inches="tight",
                pad_inches=0.3, facecolor="white")
    plt.close(fig)
    print("wrote 08-plan.png")


if __name__ == "__main__":
    d1_problem(); d2_bigpicture(); d3_pillars(); d4_journey()
    d5_safety(); d6_warning(); d7_residency(); d8_plan()
    print("\nAll diagrams written to", OUT)
