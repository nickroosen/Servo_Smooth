"""Generate docs/schematic.svg (the wiring schematic shown in README.md).

Run from the repo root:  python3 docs/make_schematic.py
"""

from pathlib import Path

W, H = 1380, 900

C20 = "#c62828"   # 20 V
C6 = "#e67700"    # 6 V servo power
C5 = "#6a3fb5"    # 5 V logic power
CG = "#333333"    # ground
CSIG = "#2e8b3a"  # servo/PIR signals
CAUD = "#1565c0"  # speaker
INK = "#222222"
MUTED = "#666666"
BOX_FILL = "#f7f7f7"

out = []


def add(s):
    out.append(s)


def text(x, y, s, size=13, anchor="start", weight="normal", color=INK, italic=False):
    style = ' font-style="italic"' if italic else ""
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    add(f'<text x="{x}" y="{y}" font-size="{size}" text-anchor="{anchor}" '
        f'font-weight="{weight}" fill="{color}"{style}>{s}</text>')


def wire(points, color, width=2.5):
    pts = " ".join(f"{x},{y}" for x, y in points)
    add(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="{width}" '
        f'stroke-linejoin="round" stroke-linecap="round"/>')


def dot(x, y, color):
    add(f'<circle cx="{x}" cy="{y}" r="4.5" fill="{color}"/>')


def ground(x, y):
    """Ground symbol hanging from (x, y)."""
    wire([(x, y), (x, y + 14)], CG)
    for i, half in enumerate((11, 7, 3)):
        yy = y + 14 + i * 5
        add(f'<line x1="{x - half}" y1="{yy}" x2="{x + half}" y2="{yy}" '
            f'stroke="{CG}" stroke-width="2.5" stroke-linecap="round"/>')


def box(x, y, w, h, title, subtitle=None):
    add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="{BOX_FILL}" '
        f'stroke="{INK}" stroke-width="2"/>')
    text(x + w / 2, y + 22, title, 14, "middle", "bold")
    if subtitle:
        for i, line in enumerate(subtitle.split("\n")):
            text(x + w / 2, y + 40 + i * 16, line, 12, "middle", color=MUTED)


def pin(x, y, label, side):
    """Pin label just inside a box edge. side = where the wire leaves."""
    add(f'<circle cx="{x}" cy="{y}" r="3" fill="{INK}"/>')
    if side == "left":
        text(x + 8, y + 4, label, 12)
    elif side == "right":
        text(x - 8, y + 4, label, 12, "end")
    elif side == "top":
        text(x, y + 18, label, 12, "middle")
    elif side == "bottom":
        text(x, y - 9, label, 12, "middle")


def cap(x, y_top, name, value, color, label_side="right"):
    """Vertical polarised capacitor from a rail at y_top down to ground."""
    p1 = y_top + 40
    wire([(x, y_top), (x, p1)], color)
    add(f'<line x1="{x - 15}" y1="{p1}" x2="{x + 15}" y2="{p1}" stroke="{INK}" stroke-width="3"/>')
    add(f'<path d="M {x - 15} {p1 + 14} Q {x} {p1 + 6} {x + 15} {p1 + 14}" fill="none" '
        f'stroke="{INK}" stroke-width="3"/>')
    sign = -1 if label_side == "right" else 1
    text(x + sign * 22, p1 - 4, "+", 14, "middle", "bold")
    wire([(x, p1 + 10), (x, p1 + 34)], CG)
    ground(x, p1 + 34)
    if label_side == "right":
        text(x + 22, p1 + 4, name, 13, weight="bold")
        text(x + 22, p1 + 20, value, 12, color=MUTED)
    else:
        text(x - 22, p1 + 4, name, 13, "end", "bold")
        text(x - 22, p1 + 20, value, 12, "end", color=MUTED)
    dot(x, y_top, color)


def net_label(x, y, s, color):
    text(x, y, s, 12, "middle", "bold", color)


add(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
    f'viewBox="0 0 {W} {H}" font-family="Helvetica, Arial, sans-serif">')
add(f'<rect width="{W}" height="{H}" fill="#ffffff"/>')

text(30, 38, "Animatronic Body Bag: wiring", 22, weight="bold")
text(30, 60, "RP2040 Prop-Maker Feather, 2 × DS3240MG (270°), PIR, one speaker, USB-C PD power",
     13, color=MUTED)

# --- USB-C charger and trigger board -----------------------------------------
box(30, 90, 170, 70, "USB-C PD charger", "65 W+, 20 V ≥ 3.25 A")
wire([(115, 160), (115, 200)], INK, 3)
text(125, 185, "USB-C cable, 60 W+", 11, color=MUTED)
box(30, 200, 170, 100, "PD trigger board", "set to 20 V\n≥ 3 A")
pin(200, 230, "+", "right")
pin(200, 270, "−", "right")
wire([(200, 270), (225, 270)], CG)
ground(225, 270)

# --- Fuse and 20 V rail --------------------------------------------------------
wire([(200, 230), (240, 230)], C20)
add(f'<rect x="240" y="221" width="56" height="18" rx="3" fill="#fff" stroke="{INK}" stroke-width="2"/>')
add(f'<line x1="240" y1="230" x2="296" y2="230" stroke="{INK}" stroke-width="1.5"/>')
text(268, 214, "F1  5 A", 12, "middle", "bold")
wire([(296, 230), (480, 230)], C20)
net_label(345, 222, "20 V", C20)

# 20 V down to the buck
dot(330, 230, C20)
wire([(330, 230), (330, 560), (480, 560)], C20)

cap(432, 230, "C1", "470 µF 35 V", C20, label_side="left")

# --- 6 V UBEC ------------------------------------------------------------------
box(480, 195, 210, 125, "6 V UBEC", "8 A, 7–25.5 V in\njumper on 6.0 V")
pin(480, 230, "IN+", "left")
pin(480, 290, "IN−", "left")
pin(690, 230, "OUT+", "right")
pin(690, 290, "OUT−", "right")
wire([(480, 290), (462, 290)], CG)
ground(462, 290)
wire([(690, 290), (715, 290)], CG)
ground(715, 290)

# 6 V rail to servos
wire([(690, 230), (1040, 230), (1040, 170)], C6)
net_label(725, 222, "6 V", C6)
cap(760, 230, "C2", "1000 µF", C6)
dot(830, 230, C6)
wire([(830, 230), (830, 170)], C6)

# --- Servos --------------------------------------------------------------------
for x0, name, sig_x in ((790, "Servo 1", 920), (1000, "Servo 2", 1130)):
    box(x0, 80, 170, 90, name, "DS3240MG 270°")
    vplus, gnd = x0 + 40, x0 + 85
    pin(vplus, 170, "V+", "bottom")
    pin(gnd, 170, "GND", "bottom")
    pin(sig_x, 170, "SIG", "bottom")
    wire([(gnd, 170), (gnd, 186)], CG)
    ground(gnd, 186)

# --- 5 V buck ------------------------------------------------------------------
box(480, 525, 210, 125, "5 V buck", "1–2 A out\n≥ 24 V in")
pin(480, 560, "IN+", "left")
pin(480, 620, "IN−", "left")
pin(690, 560, "OUT+", "right")
pin(690, 620, "OUT−", "right")
wire([(480, 620), (455, 620)], CG)
ground(455, 620)
wire([(690, 620), (715, 620)], CG)
ground(715, 620)

wire([(690, 560), (850, 560)], C5)
net_label(725, 552, "5 V", C5)
cap(770, 560, "C3", "220 µF", C5)

# --- Feather -------------------------------------------------------------------
FX, FY, FW, FH = 850, 450, 240, 330
add(f'<rect x="{FX}" y="{FY}" width="{FW}" height="{FH}" rx="8" fill="{BOX_FILL}" '
    f'stroke="{INK}" stroke-width="2"/>')
text(FX + FW / 2, FY + 330 / 2 - 8, "RP2040 Prop-Maker", 15, "middle", "bold")
text(FX + FW / 2, FY + 330 / 2 + 12, "Feather", 14, "middle", "bold")
pin(FX, 560, "USB", "left")
pin(FX, 620, "GND", "left")
wire([(FX, 620), (832, 620), (832, 650)], CG)
ground(832, 650)

# Servo signals into the top of the Feather
pin(920, FY, "D9", "top")
pin(1010, FY, "D10", "top")
wire([(920, 170), (920, FY)], CSIG)
wire([(1130, 170), (1130, 390), (1010, 390), (1010, FY)], CSIG)

# Terminal block on the right
terms = [(520, "5V"), (560, "G"), (600, "Btn"), (680, "+"), (720, "−")]
for y, label in terms:
    pin(FX + FW, y, label, "right")
text(FX + FW - 8, 500, "terminal block", 11, "end", color=MUTED, italic=True)
text(FX + 20, 755, "servo header: not used", 11, color=MUTED, italic=True)

# --- PIR -----------------------------------------------------------------------
box(1200, 480, 150, 145, "PIR sensor")
text(1340, 580, "time knob: min", 11, "end", color=MUTED)
text(1340, 596, "jumper: H", 11, "end", color=MUTED)
pin(1200, 520, "VCC", "left")
pin(1200, 560, "GND", "left")
pin(1200, 600, "OUT", "left")
wire([(FX + FW, 520), (1200, 520)], C5)
wire([(FX + FW, 560), (1200, 560)], CG)
wire([(FX + FW, 600), (1200, 600)], CSIG)

# --- Speaker -------------------------------------------------------------------
box(1200, 650, 150, 100, "Speaker", "4–8 Ω, ≤ 3 W")
pin(1200, 680, "+", "left")
pin(1200, 720, "−", "left")
wire([(FX + FW, 680), (1200, 680)], CAUD)
wire([(FX + FW, 720), (1200, 720)], CAUD)

# --- Legend and notes ----------------------------------------------------------
LX, LY = 30, 360
add(f'<rect x="{LX}" y="{LY}" width="280" height="170" rx="8" fill="#fff" '
    f'stroke="#bbbbbb" stroke-width="1.5"/>')
text(LX + 14, LY + 24, "Legend", 14, weight="bold")
for i, (color, label) in enumerate([(C20, "20 V from trigger board"),
                                    (C6, "6 V servo power (18 AWG)"),
                                    (C5, "5 V Feather / PIR power"),
                                    (CG, "Ground"),
                                    (CSIG, "Signal"),
                                    (CAUD, "Speaker")]):
    y = LY + 46 + i * 20
    wire([(LX + 14, y - 4), (LX + 54, y - 4)], color, 3)
    text(LX + 64, y, label, 12)

ground(LX + 30, 700)
text(LX + 50, 722, "All grounds are connected together", 13, weight="bold")
text(LX + 50, 740, "(common ground: trigger −, UBEC, buck, Feather, servos, PIR)", 12,
     color=MUTED)
dot(LX + 22, 762, INK)
text(LX + 50, 766, "Dot = joined. Wires crossing without a dot are not connected.", 12,
     color=MUTED)

notes = [
    "Before connecting the Feather or servos, measure with a multimeter:",
    "  trigger board 20 V  ·  UBEC out 6.0 V (not 7.4 V)  ·  buck out 4.9–5.2 V",
    "Capacitors: stripe (−) to ground, keep leads short. C2 close to the servo power split.",
    "Don't plug the Feather into a computer while the buck is connected (disconnect buck +).",
]
for i, line in enumerate(notes):
    text(30, 812 + i * 20, line, 12, color=INK if i == 0 else MUTED,
         weight="bold" if i == 0 else "normal")

add("</svg>")

Path(__file__).with_name("schematic.svg").write_text("\n".join(out) + "\n", encoding="utf-8")
