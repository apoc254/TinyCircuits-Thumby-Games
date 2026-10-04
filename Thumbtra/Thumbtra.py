# IRONFIRE - run & gun shooter for Thumby (MicroPython)
#
#  D-pad : move      UP : aim up (UP + direction = diagonal)
#  DOWN  : duck (low hitbox, low shots)
#  A     : jump (DOWN + A drops through a platform)
#  B     : fire (hold for auto-fire)
#
#  ONE HIT KILLS.  3 lives per stage run.  Power-up capsules fly past -
#  shoot them, then grab what drops:
#     M = more bullets per shot (1 -> 2 -> 3)     R = faster fire rate
#  4 stages, each ending in a boss:
#     1 JUNGLE   - TANK        (100 hits, charges to run you over)
#     2 CITY     - HELICOPTER  (flies at varied heights)
#     3 HARBOR   - SUBMARINE   (only hittable while surfaced)
#     4 FORTRESS - MECH        (shoots, punches, jumps around)

import thumby
import math
import random

D = thumby.display
D.setFPS(30)

GY = 32                 # ground surface
GRAV = 0.3
JUMPV = -3.4
SPEED = 1.2
MAXEB = 70
MAXPB = 26
RATE = (10, 6, 4)       # frames between shots by rate level
MULT = ((0.0,), (-0.1, 0.1), (-0.24, 0.0, 0.24))   # bullet angles by multi level

RUN, RIF, TUR, DRN, CAP, LEP, PIK = range(7)
EW = (5, 5, 8, 8, 9, 5, 7)
EH = (8, 8, 6, 5, 6, 6, 9)
EHP = (1, 1, 3, 1, 1, 1, 1)
ESC = (100, 200, 300, 150, 500, 100, 0)
D8 = ((1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1))


class Obj:
    pass


# ------------------------------------------------------------ draw helpers
def px(x, y):
    x = int(x)
    y = int(y)
    if 0 <= x < 72 and 0 <= y < 40:
        D.setPixel(x, y, 1)


def lineS(x0, y0, x1, y1):
    n = int(max(abs(x1 - x0), abs(y1 - y0)))
    if n == 0:
        px(x0, y0)
        return
    for i in range(n + 1):
        px(x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * i / n)


def frect(x, y, w, h, c=1):
    x = int(x)
    y = int(y)
    x0 = max(0, x)
    y0 = max(0, y)
    x1 = min(72, x + int(w))
    y1 = min(40, y + int(h))
    if x1 > x0 and y1 > y0:
        D.drawFilledRectangle(x0, y0, x1 - x0, y1 - y0, c)


def orect(x, y, w, h):
    frect(x, y, w, 1)
    frect(x, y + h - 1, w, 1)
    frect(x, y, 1, h)
    frect(x + w - 1, y, 1, h)


def beep(f, ms):
    try:
        thumby.audio.play(f, ms)
    except Exception:
        pass


def center(text, y):
    D.drawText(text, (72 - len(text) * 6) // 2, y, 1)


# ----------------------------------------------------------------- sprites
def mk_spr(art, flip):
    h = len(art)
    w = len(art[0])
    n = (h + 7) >> 3
    bm = bytearray(w * n)
    mk = bytearray(w * n)
    g = [[art[y][(w - 1 - x) if flip else x] != '.' for x in range(w)]
         for y in range(h)]
    for y in range(h):
        for x in range(w):
            near = False
            for yy in range(max(0, y - 1), min(h, y + 2)):
                for xx in range(max(0, x - 1), min(w, x + 2)):
                    if g[yy][xx]:
                        near = True
            i = (y >> 3) * w + x
            if g[y][x]:
                bm[i] |= 1 << (y & 7)
            if near:
                mk[i] |= 1 << (y & 7)
    return (bm, mk, w, h)


def S(art):
    return (mk_spr(art, False), mk_spr(art, True))


def BIG(art):
    out = []
    for y0 in range(0, len(art), 8):
        out.append((y0, S(art[y0:y0 + 8])))
    return out


def dspr(s, x, y, face):
    e = s[0] if face > 0 else s[1]
    D.blitWithMask(e[0], int(x), int(y), e[2], e[3], -1, 0, 0, e[1])


def dbig(b, x, y, left):
    for off, s in b:
        dspr(s, x, y + off, 1 if left else -1)


def cv(w, h):
    return [['.'] * w for _ in range(h)]


def fl(c, x, y, w, h, ch='#'):
    for yy in range(y, y + h):
        for xx in range(x, x + w):
            if 0 <= yy < len(c) and 0 <= xx < len(c[0]):
                c[yy][xx] = ch


def rows(c):
    return [''.join(r) for r in c]


def dither(art):
    return [''.join(ch if (x + y) % 2 == 0 else '.' for x, ch in enumerate(r))
            for y, r in enumerate(art)]


def tile(r8):
    b = bytearray(8)
    for x in range(8):
        for y in range(8):
            if r8[y][x] != '.':
                b[x] |= 1 << y
    return b


# player (facing right)
SP_STAND = S((".##..", ".##..", "####.", ".##..", ".##..", ".#.#.", ".#.#.", ".#.#."))
SP_RUN1 = S((".##..", ".##..", "####.", ".##..", ".##..", "#..#.", "#..#.", "#...#"))
SP_RUN2 = S((".##..", ".##..", "####.", ".##..", ".##..", "..#..", ".#.#.", ".#.#."))
SP_JUMP = S((".####.", "######", "##..##", "##..##", "######", ".####."))
SP_PRONE = S(("....###.", "########", "########", ".#....#."))
# enemies (facing right)
SP_RUNNER = (S((".###.", "#####", ".#.#.", ".###.", "#####", ".###.", ".#.#.", "##.##")),
             S((".###.", "#####", ".#.#.", ".###.", "#####", ".###.", "..#..", ".#.#.")))
SP_RIF = S(("#####", "#.#.#", ".###.", ".###.", "#####", ".###.", ".#.#.", ".#.#."))
SP_TUR = S(("..####..", ".######.", "########", "##.##.##", "########", "########"))
SP_DRN = (S(("#......#", "##.##.##", ".######.", "..####..", "...##...")),
          S(("..####..", ".######.", "##.##.##", "#..##..#", "...##...")))
SP_CAP = S(("..#####..", ".#######.", "####.####", "####.####", ".#######.", "..#####.."))
SP_LEP = S((".###.", "#####", "##.##", "#####", ".###.", "..#.."))


def tank_art():
    c = cv(22, 11)
    fl(c, 8, 0, 8, 4)
    fl(c, 2, 4, 19, 3)
    fl(c, 0, 5, 3, 2)
    fl(c, 0, 7, 22, 4)
    for x in range(2, 20, 4):
        fl(c, x, 8, 2, 2, '.')
    fl(c, 4, 5, 3, 1, '.')
    return rows(c)


def heli_art():
    c = cv(22, 10)
    fl(c, 10, 1, 2, 2)
    fl(c, 3, 3, 12, 5)
    fl(c, 1, 4, 3, 3)
    fl(c, 15, 4, 6, 2)
    fl(c, 19, 1, 2, 5)
    fl(c, 4, 8, 11, 1)
    fl(c, 5, 7, 1, 2)
    fl(c, 12, 7, 1, 2)
    fl(c, 3, 4, 4, 2, '.')
    return rows(c)


def hull_art():
    c = cv(24, 8)
    fl(c, 3, 0, 18, 8)
    fl(c, 1, 1, 22, 6)
    fl(c, 0, 2, 24, 4)
    for x in (8, 12, 16):
        fl(c, x, 3, 2, 2, '.')
    return rows(c)


def tower_art():
    c = cv(8, 7)
    fl(c, 5, 0, 2, 3)
    fl(c, 1, 2, 6, 5)
    fl(c, 3, 3, 2, 2, '.')
    return rows(c)


def mech_art(kind):
    c = cv(14, 24)
    fl(c, 4, 0, 6, 5)
    fl(c, 4, 2, 3, 1, '.')
    fl(c, 3, 5, 9, 8)
    fl(c, 5, 7, 5, 2, '.')
    fl(c, 0, 5, 3, 7)
    fl(c, 11, 6, 3, 5)
    fl(c, 3, 13, 9, 3)
    if kind == 0:
        fl(c, 3, 16, 3, 6)
        fl(c, 9, 16, 3, 6)
        fl(c, 2, 22, 5, 2)
        fl(c, 8, 22, 5, 2)
    elif kind == 1:
        fl(c, 2, 16, 3, 6)
        fl(c, 10, 16, 3, 5)
        fl(c, 1, 22, 5, 2)
        fl(c, 9, 21, 5, 2)
    else:
        fl(c, 2, 16, 4, 4)
        fl(c, 9, 16, 4, 4)
        fl(c, 1, 20, 5, 2)
        fl(c, 9, 20, 5, 2)
    return rows(c)


SP_TANK = BIG(tank_art())
SP_HELI = BIG(heli_art())
SP_HULL = BIG(hull_art())
SP_HULLD = BIG(dither(hull_art()))
SP_TOWER = BIG(tower_art())
SP_MECH = [BIG(mech_art(0)), BIG(mech_art(1)), BIG(mech_art(2))]

TILES = [
    tile(["########", "########", "#.#.#.#.", ".#...#..", "...#...#", "#...#...", ".#...#..", "...#...#"]),
    tile(["########", "########", "#......#", "########", "........", "#..#..#.", "########", "........"]),
    tile(["########", "########", "##.#####", "########", "####.###", "########", "###.####", "########"]),
    tile(["########", "########", ".#.##.#.", "#..##..#", "..#..#..", ".#....#.", "#.#..#.#", "..#..#.."]),
]
WAVE = [
    tile(["##..##..", "........", "..#...#.", "........", ".#...#..", "........", "#...#...", "........"]),
    tile(["..##..##", "........", ".#...#..", "........", "..#...#.", "........", "...#...#", "........"]),
]

# -------------------------------------------------------------- level data
# spawns: (x, kind, y, arg)   y = feet for ground units, top for DRN/CAP
# TUR arg: 0 aimed, 1 three-way, 2 ring.   RIF arg 1 = double shot
# DRN arg 1 = bomber.  CAP arg = 'M' or 'R'
L1 = ("JUNGLE", 720, 0, False,
      [(0, 184), (200, 360), (376, 520), (536, 720)],
      [(56, 88, 24), (112, 144, 16), (216, 248, 24), (256, 288, 18), (300, 332, 24),
       (392, 424, 24), (408, 440, 16), (456, 488, 22), (552, 584, 24), (568, 600, 18),
       (656, 672, 20), (688, 704, 20)],
      [(90, RUN, 32, 0), (106, RUN, 32, 0), (140, RIF, 32, 0), (160, CAP, 18, 'R'),
       (205, RUN, 32, 0), (219, RUN, 32, 0), (240, RIF, 24, 0), (262, TUR, 32, 0),
       (312, RIF, 24, 1), (330, RUN, 32, 0), (344, RUN, 32, 0), (345, CAP, 16, 'M'),
       (400, RIF, 24, 0), (424, RIF, 16, 1), (440, RUN, 32, 0), (460, TUR, 32, 0),
       (470, RIF, 22, 0), (500, RUN, 32, 0), (512, RUN, 32, 0), (545, RUN, 32, 0),
       (560, RIF, 24, 1), (575, RIF, 18, 0), (595, TUR, 32, 0), (610, RUN, 32, 0),
       (622, RUN, 32, 0), (630, CAP, 18, 'R')])

L2 = ("CITY", 760, 1, False,
      [(0, 152), (168, 296), (312, 456), (472, 600), (616, 760)],
      [(40, 72, 22), (88, 120, 16), (184, 216, 24), (200, 232, 16), (240, 272, 22),
       (328, 360, 24), (344, 368, 16), (392, 424, 22), (488, 520, 24), (504, 536, 18),
       (552, 584, 22), (632, 664, 24), (648, 672, 16),
       (696, 712, 22), (728, 744, 22), (712, 728, 15)],
      [(90, RUN, 32, 0), (104, RIF, 16, 0), (120, RUN, 32, 0),
       (150, DRN, 12, 0), (166, DRN, 12, 0), (182, DRN, 12, 0),
       (190, RIF, 24, 0), (210, RIF, 16, 1), (235, TUR, 32, 1), (250, CAP, 18, 'M'),
       (256, RIF, 22, 0), (285, RUN, 32, 0), (320, DRN, 10, 1), (336, DRN, 10, 1),
       (335, RIF, 24, 0), (350, RIF, 16, 1), (375, RUN, 32, 0), (390, RUN, 32, 0),
       (405, RIF, 22, 0), (420, TUR, 32, 1), (440, RUN, 32, 0), (450, CAP, 16, 'R'),
       (480, DRN, 14, 0), (494, DRN, 14, 0), (508, DRN, 14, 0), (522, DRN, 14, 0),
       (495, RIF, 24, 1), (510, RIF, 18, 0), (540, TUR, 32, 1), (560, RIF, 22, 0),
       (575, RUN, 32, 0), (588, RUN, 32, 0), (620, RUN, 32, 0), (640, RIF, 24, 1),
       (655, RIF, 16, 0), (670, DRN, 12, 1), (676, CAP, 18, 'M')])

L3 = ("HARBOR", 760, 2, True,
      [(0, 136), (160, 248), (264, 376), (392, 472), (496, 600), (616, 720)],
      [(40, 72, 24), (100, 124, 18), (144, 152, 28), (176, 208, 24), (192, 216, 16),
       (280, 312, 22), (296, 320, 16), (344, 368, 24), (420, 452, 24), (436, 460, 17),
       (480, 488, 28), (520, 552, 22), (536, 568, 16), (632, 664, 24),
       (696, 710, 20), (722, 734, 28)],
      [(70, RUN, 32, 0), (86, RUN, 32, 0), (110, RIF, 18, 0), (148, LEP, 0, 0),
       (170, RUN, 32, 0), (185, RIF, 24, 1), (200, DRN, 12, 0), (214, DRN, 12, 0),
       (225, TUR, 32, 1), (240, CAP, 18, 'M'), (256, LEP, 0, 0), (285, RIF, 22, 0),
       (300, RUN, 32, 0), (318, RIF, 16, 1), (330, DRN, 10, 1), (344, DRN, 10, 1),
       (355, TUR, 32, 1), (384, LEP, 0, 0), (400, RUN, 32, 0), (412, RUN, 32, 0),
       (430, RIF, 24, 0), (445, RIF, 17, 1), (460, CAP, 18, 'R'), (484, LEP, 0, 0),
       (505, RUN, 32, 0), (525, RIF, 22, 1), (540, RIF, 16, 0), (545, TUR, 32, 1),
       (560, DRN, 14, 0), (574, DRN, 14, 0), (588, DRN, 14, 0), (608, LEP, 0, 0),
       (625, RUN, 32, 0), (640, RIF, 24, 1), (655, RUN, 32, 0), (670, CAP, 18, 'M')])

L4 = ("FORTRESS", 720, 3, False,
      [(0, 168), (184, 336), (352, 480), (496, 720)],
      [(48, 80, 24), (104, 136, 18), (200, 232, 24), (216, 248, 16), (264, 296, 22),
       (368, 400, 24), (384, 416, 16), (424, 456, 22), (520, 552, 24), (536, 568, 17),
       (584, 616, 22), (656, 672, 22), (688, 704, 22)],
      [(80, RUN, 32, 0), (96, RUN, 32, 0), (120, TUR, 32, 2), (140, RIF, 18, 1),
       (150, DRN, 12, 0), (164, DRN, 12, 0), (178, DRN, 12, 0), (190, CAP, 18, 'M'),
       (215, RIF, 24, 1), (235, RIF, 16, 1), (255, TUR, 32, 2), (270, RIF, 22, 1),
       (290, RUN, 32, 0), (305, RUN, 32, 0), (320, DRN, 10, 1), (334, DRN, 10, 1),
       (360, TUR, 32, 1), (375, RIF, 24, 1), (390, RIF, 16, 1), (410, TUR, 32, 2),
       (430, RIF, 22, 1), (445, RUN, 32, 0), (460, CAP, 18, 'R'), (505, DRN, 14, 0),
       (519, DRN, 14, 0), (533, DRN, 14, 0), (547, DRN, 14, 0), (525, RIF, 24, 1),
       (545, RIF, 17, 1), (560, TUR, 32, 2), (590, RIF, 22, 1), (600, RUN, 32, 0),
       (612, RUN, 32, 0), (625, TUR, 32, 1), (635, CAP, 18, 'M')])

LEVELS = (L1, L2, L3, L4)

# ------------------------------------------------------------- global state
mode = "title"
level = 0
sel_lvl = 0
maxlvl = 0
hi = 0
score = 0
lvl_score = 0
lvl_mult = 0
lvl_rate = 0
T = 0
cam = 0.0
CX = 0
SHK = 0
LEN = 720
THEME = 0
WATER = False
PL = []
GMAP = []
SP = []
EN = []
EB = []
PB = []
FX = []
BO = None
boss_done = False
card_t = 0
clear_t = 0
PCX = 0.0
PCY = 0.0
P = Obj()
P.lives = 3
P.mult = 0
P.rate = 0


def load_save():
    global hi, maxlvl
    try:
        thumby.saveData.setName("Ironfire")
        if thumby.saveData.hasItem("hi"):
            hi = int(thumby.saveData.getItem("hi"))
        if thumby.saveData.hasItem("lv"):
            maxlvl = min(3, int(thumby.saveData.getItem("lv")))
    except Exception:
        pass


def store_save():
    try:
        thumby.saveData.setItem("hi", hi)
        thumby.saveData.setItem("lv", maxlvl)
        thumby.saveData.save()
    except Exception:
        pass


# ----------------------------------------------------------------- helpers
def floor_at(cx, y0, y1, nodrop=False):
    best = None
    for pl in PL:
        if pl[0] - 1 <= cx <= pl[1] + 1:
            y = pl[2]
            if y0 <= y + 0.01 and y1 >= y - 0.01:
                if nodrop and y < GY:
                    continue
                if best is None or y < best:
                    best = y
    return best


def ground_at(x):
    for pl in PL:
        if pl[2] == GY and pl[0] <= x <= pl[1]:
            return True
    return False


def boom(x, y, big=True):
    if len(FX) < 24:
        FX.append([x, y, 0, 12 if big else 6])


def ebul(x, y, a, spd, kind=0, aux=0.0):
    if len(EB) < MAXEB:
        EB.append([x, y, math.cos(a) * spd, math.sin(a) * spd, kind, aux])


def aim_at(x, y):
    return math.atan2(PCY - y, PCX - x)


def shoot_aimed(x, y, spd=1.1, off=0.0):
    ebul(x, y, aim_at(x, y) + off, spd)


def ring(x, y, n, spd, rot=0.0):
    for i in range(n):
        ebul(x, y, rot + i * 6.2832 / n, spd)


def mortar(x, y, tx, t=54.0):
    if len(EB) < MAXEB:
        EB.append([x, y, (tx - x) / t, -0.035 * t, 1, 0.0])


def pbox():
    if P.prone:
        return (P.x - 1, P.y - 3, P.x + 6, P.y - 1)
    if not P.gr:
        return (P.x + 1, P.y - 5, P.x + 4, P.y - 1)
    return (P.x + 1, P.y - 7, P.x + 4, P.y - 1)


def hit_p(x, y):
    l, t, r, b = pbox()
    return l - 1 < x < r + 1 and t - 1 < y < b + 1


def box_p(l2, t2, r2, b2):
    l, t, r, b = pbox()
    return l < r2 and r > l2 and t < b2 and b > t2


# ------------------------------------------------------------------ player
def reset_player():
    P.x = 6.0
    P.y = 0.0
    P.vy = 0.0
    P.gr = False
    P.face = 1
    P.prone = False
    P.dead = 0
    P.inv = 60
    P.cd = 0
    P.an = 0
    P.drop = 0
    P.ax = 1.0
    P.ay = 0.0


def kill_player():
    if P.dead or P.inv:
        return
    P.dead = 45
    P.lives -= 1
    P.mult = max(0, P.mult - 1)
    P.rate = max(0, P.rate - 1)
    for i in range(4):
        boom(P.x + random.randint(0, 5), P.y - random.randint(2, 8))
    beep(120, 250)


def respawn():
    reset_player()
    x = cam + 10.0
    while x < cam + 56:
        ok = True
        for d in (-3, 0, 5, 10, 15, 20):
            if not ground_at(x + d):
                ok = False
        if ok:
            break
        x += 2.0
    P.x = x
    P.y = float(GY)
    P.gr = True
    P.inv = 90
    EB[:] = [b for b in EB if abs(b[0] - x) > 40]


def fire():
    P.cd = RATE[P.rate]
    cx = P.x + 2.5
    if P.prone:
        cy = P.y - 2.0
    elif P.gr:
        cy = P.y - 5.0
    else:
        cy = P.y - 3.0
    mx = cx + P.ax * 6
    my = cy + P.ay * 6
    base = math.atan2(P.ay, P.ax)
    for off in MULT[P.mult]:
        if len(PB) < MAXPB:
            a = base + off
            PB.append([mx, my, math.cos(a) * 3.6, math.sin(a) * 3.6, 22])


def update_player():
    global PCX, PCY
    if P.dead:
        P.dead -= 1
        if P.dead == 0:
            if P.lives <= 0:
                game_over()
            else:
                respawn()
        return
    if P.inv:
        P.inv -= 1
    if P.cd:
        P.cd -= 1
    l = thumby.buttonL.pressed()
    r = thumby.buttonR.pressed()
    u = thumby.buttonU.pressed()
    d = thumby.buttonD.pressed()
    dx = (1 if r else 0) - (1 if l else 0)
    if dx:
        P.face = dx
    jp = thumby.buttonA.justPressed()
    held = thumby.buttonA.pressed()
    P.prone = bool(P.gr and d and not u)
    cx = P.x + 2.5
    if jp:
        if P.prone:
            if P.y < GY - 0.5:
                P.drop = 10
                P.gr = False
                P.vy = 0.5
        elif P.gr:
            P.vy = JUMPV
            P.gr = False
    if not P.prone and dx:
        P.x += dx * SPEED
        P.an += 1
    hi_x = min(cam + 67.0, LEN - 5.0)
    if P.x < cam:
        P.x = cam
    if P.x > hi_x:
        P.x = hi_x
    cx = P.x + 2.5
    if P.drop:
        P.drop -= 1
    if P.gr:
        if floor_at(cx, P.y, P.y + 1.5, P.drop > 0) is None:
            P.gr = False
    if not P.gr:
        if not held and P.vy < -1.6:
            P.vy = -1.6
        P.vy = min(P.vy + GRAV, 4.0)
        ny = P.y + P.vy
        if P.vy >= 0:
            f = floor_at(cx, P.y, ny, P.drop > 0)
            if f is not None:
                P.y = f
                P.vy = 0.0
                P.gr = True
            else:
                P.y = ny
        else:
            P.y = ny
    if P.y > (35 if WATER else 46):
        P.inv = 0
        if WATER:
            boom(P.x + 2, 33, False)
        kill_player()
        return
    # aim: forward, up, or diagonal up
    if P.prone:
        P.ax = float(P.face)
        P.ay = 0.0
    elif u:
        if dx:
            P.ax = dx * 0.7071
            P.ay = -0.7071
        else:
            P.ax = 0.0
            P.ay = -1.0
    else:
        P.ax = float(P.face)
        P.ay = 0.0
    if thumby.buttonB.pressed() and P.cd == 0:
        fire()
    PCX = P.x + 2.5
    PCY = P.y - 4.0


# ----------------------------------------------------------------- enemies
def mk_enemy(s):
    x, k, y, a = s
    e = Obj()
    e.k = k
    e.a = a
    e.w = EW[k]
    e.h = EH[k]
    e.x = float(x)
    e.vx = 0.0
    e.vy = 0.0
    if k == DRN or k == CAP:
        e.y = float(y)
        e.b = float(y)
        e.vx = -0.9 if k == DRN else -0.6
    elif k == LEP:
        e.y = 34.0
        e.vx = -0.5
    elif k == PIK:
        e.y = float(y)
    else:
        e.y = float(y - e.h)
    e.hp = EHP[k]
    e.t = random.randint(0, 30)
    e.c = 0
    e.fl = 0
    e.dead = False
    return e


def phys(e):
    e.vy = min(e.vy + GRAV, 4.0)
    fo = e.y + e.h
    f = floor_at(e.x + e.w * 0.5, fo, fo + e.vy)
    if f is not None and e.vy >= 0:
        e.y = f - e.h
        e.vy = 0.0
    else:
        e.y += e.vy


def upd_enemy(e):
    k = e.k
    e.t += 1
    sx = e.x - cam
    if k == RUN:
        e.x += 0.75 if PCX > e.x + 2 else -0.75
        phys(e)
        if e.x < cam - 14 or e.y > 46:
            e.dead = True
    elif k == RIF:
        if 0 < sx < 72 and e.t % (100 if e.a == 0 else 85) == 40:
            shoot_aimed(e.x + 2, e.y + 3, 1.0)
            if e.a == 1:
                shoot_aimed(e.x + 2, e.y + 3, 1.0, 0.18)
        if e.x < cam - 14:
            e.dead = True
    elif k == TUR:
        per = (62, 84, 120)[e.a]
        if 0 < sx < 72 and e.t % per == 0:
            ex = e.x + 4
            ey = e.y + 2
            if e.a == 0:
                shoot_aimed(ex, ey, 1.15)
            elif e.a == 1:
                for o in (-0.3, 0.0, 0.3):
                    shoot_aimed(ex, ey, 1.0, o)
            else:
                ring(ex, ey, 8, 0.8, (e.t / per) * 0.4)
        if e.x < cam - 14:
            e.dead = True
    elif k == DRN:
        e.x += e.vx
        e.y = e.b + 6 * math.sin(e.t * 0.12)
        if e.a == 0:
            if e.t == 40 and sx < 72:
                shoot_aimed(e.x + 4, e.y + 4, 1.05)
        elif e.c == 0 and abs(e.x - PCX) < 5 and sx < 72:
            e.c = 1
            ebul(e.x + 4, e.y + 5, 1.5708, 1.3)
        if e.x < cam - 14:
            e.dead = True
    elif k == CAP:
        e.x += e.vx
        e.y = e.b + 4 * math.sin(e.t * 0.09)
        if e.x < cam - 14:
            e.dead = True
    elif k == LEP:
        if e.c == 0:
            if sx < 58:
                e.c = 1
                e.vy = -3.3
        else:
            e.vy += 0.22
            e.y += e.vy
            e.x += e.vx
            if e.vy > 0 and e.y > 34:
                boom(e.x + 2, 33, False)
                e.dead = True
    elif k == PIK:
        phys(e)
        if e.y > 46 or e.x < cam - 14:
            e.dead = True


def kill_e(e):
    global score
    e.dead = True
    score += ESC[e.k]
    boom(e.x + e.w / 2, e.y + e.h / 2)
    beep(300, 40)
    if e.k == CAP:
        p = mk_enemy((e.x, PIK, e.y, e.a))
        p.y = e.y
        NEW.append(p)


NEW = []


def update_enemies():
    global score
    for e in EN:
        if not e.dead:
            upd_enemy(e)
        if e.fl:
            e.fl -= 1
    if NEW:
        EN.extend(NEW)
        del NEW[:]
    # contact
    for e in EN:
        if e.dead or P.dead:
            continue
        k = e.k
        if k == LEP and e.c == 0:
            continue
        if k == PIK:
            if box_p(e.x, e.y, e.x + e.w, e.y + e.h):
                e.dead = True
                if e.a == 'M':
                    if P.mult < 2:
                        P.mult += 1
                    else:
                        score += 500
                else:
                    if P.rate < 2:
                        P.rate += 1
                    else:
                        score += 500
                beep(900, 80)
        elif box_p(e.x + 1, e.y + 1, e.x + e.w - 1, e.y + e.h - 1):
            kill_player()
    EN[:] = [e for e in EN if not e.dead]


def spawn_check():
    i = len(SP) - 1
    while i >= 0:
        s = SP[i]
        if s[0] <= cam + 80:
            EN.append(mk_enemy(s))
            SP.pop(i)
        i -= 1


# ----------------------------------------------------------------- bullets
def update_pbul():
    i = len(PB) - 1
    while i >= 0:
        b = PB[i]
        b[0] += b[2]
        b[1] += b[3]
        b[4] -= 1
        if b[4] <= 0 or b[0] < cam - 4 or b[0] > cam + 76 or b[1] < -4 or b[1] > 40:
            PB.pop(i)
        i -= 1


def hit_pbul():
    i = len(PB) - 1
    while i >= 0:
        b = PB[i]
        x = b[0]
        y = b[1]
        gone = False
        if BO is not None and boss_hit(x, y):
            gone = True
        else:
            for e in EN:
                if e.dead or e.k == PIK:
                    continue
                if e.k == LEP and e.c == 0:
                    continue
                if e.x - 1 < x < e.x + e.w + 1 and e.y - 1 < y < e.y + e.h + 1:
                    e.hp -= 1
                    e.fl = 2
                    if e.hp <= 0:
                        kill_e(e)
                    gone = True
                    break
        if gone:
            PB.pop(i)
        i -= 1


def update_ebul():
    i = len(EB) - 1
    while i >= 0:
        b = EB[i]
        k = b[4]
        if k == 1:
            b[3] += 0.07
        b[0] += b[2]
        b[1] += b[3]
        dead = False
        if k == 2:
            if b[1] <= b[5]:
                ring(b[0], b[1], 7, 0.8, random.random() * 6.28)
                dead = True
        elif k == 1 and b[3] > 0 and b[1] >= GY - 1:
            dead = True
            boom(b[0], b[1], False)
        if b[0] < cam - 8 or b[0] > cam + 80 or b[1] < -8 or b[1] > 44:
            dead = True
        if not dead and not P.dead and not P.inv:
            if k == 4:
                hit = box_p(b[0] - 3, b[1] - 1, b[0] + 3, b[1] + 1)
            else:
                hit = hit_p(b[0], b[1])
            if hit:
                kill_player()
                dead = True
        if dead:
            EB.pop(i)
        i -= 1


def update_fx():
    i = len(FX) - 1
    while i >= 0:
        f = FX[i]
        f[2] += 1
        if f[2] >= f[3]:
            FX.pop(i)
        i -= 1


# ------------------------------------------------------------------ bosses
def new_boss(k):
    b = Obj()
    b.k = k
    b.t = 0
    b.intro = 70
    b.dying = 0
    b.flash = 0
    b.state = ''
    b.st = 0
    b.face = -1
    b.vx = 0.0
    b.vy = 0.0
    b.jit = 0
    b.pat = 0
    b.n = 0
    b.cols = []
    b.tx = 0.0
    b.ty = 0.0
    b.dir = -1
    b.fr = 0
    c = float(cam)
    if k == 0:
        b.mhp = b.hp = 100
        b.x = c + 76.0
        b.y = float(GY - 11)
        b.tx = c + 46.0
        b.state = 'in'
    elif k == 1:
        b.mhp = b.hp = 60
        b.x = c + 76.0
        b.y = 10.0
        b.tx = c + 38.0
        b.ty = 10.0
        b.state = 'move'
    elif k == 2:
        b.mhp = b.hp = 60
        b.x = c + 46.0
        b.y = 33.0
        b.state = 'track'
    else:
        b.mhp = b.hp = 90
        b.x = c + 80.0
        b.y = float(GY - 24)
        b.vx = -1.4
        b.vy = -3.5
        b.state = 'in'
    return b


def boss_box():
    b = BO
    k = b.k
    if k == 0:
        if b.state == 'away':
            return None
        return (b.x, b.y, b.x + 22, b.y + 11)
    if k == 1:
        return (b.x + 1, b.y + 2, b.x + 21, b.y + 9)
    if k == 2:
        if b.y <= 30:
            return (b.x + 1, b.y - 6, b.x + 23, 31)
        return None
    return (b.x + 1, b.y, b.x + 13, b.y + 24)


def boss_hit(x, y):
    b = BO
    if b.intro > 0 or b.dying:
        return False
    bx = boss_box()
    if bx is None:
        return False
    if bx[0] - 1 < x < bx[2] + 1 and bx[1] - 1 < y < bx[3] + 1:
        b.hp -= 1
        b.flash = 2
        boom(x, y, False)
        if b.hp <= 0:
            boss_die()
        return True
    return False


def boss_die():
    global score
    BO.dying = 1
    score += 2000
    del EB[:]
    beep(100, 400)


def boss_contact():
    b = BO
    k = b.k
    z = None
    if k == 0:
        if b.state != 'away':
            z = (b.x + 1, b.y + 3, b.x + 21, b.y + 11)
    elif k == 1:
        z = (b.x + 3, b.y + 3, b.x + 19, b.y + 9)
    elif k == 2:
        if b.y <= 30:
            z = (b.x + 1, b.y, b.x + 23, 31)
    else:
        z = (b.x + 2, b.y + 1, b.x + 12, b.y + 24)
        if b.state == 'punch' and b.st >= 12:
            cx = b.x + 7
            if b.face < 0:
                z2 = (cx - 19, b.y + 4, cx - 4, b.y + 14)
            else:
                z2 = (cx + 4, b.y + 4, cx + 19, b.y + 14)
            if box_p(z2[0], z2[1], z2[2], z2[3]):
                kill_player()
    if z is not None and box_p(z[0], z[1], z[2], z[3]):
        kill_player()


def shake(n):
    global SHK
    SHK = max(SHK, n)


# --- tank
def tank_aim(b):
    cx = b.x + 11
    cy = b.y + 2
    a = math.atan2(PCY - cy, PCX - cx)
    if math.sin(a) > 0.3:
        a = 3.1416 if math.cos(a) < 0 else 0.0
    return cx + math.cos(a) * 10, cy + math.sin(a) * 10, a


def upd_tank(b):
    s = b.state
    b.st += 1
    b.jit = 0
    fast = b.hp < 40
    if s == 'in':
        d = 1 if b.tx > b.x else -1
        b.x += d * 1.1
        b.face = -d
        if abs(b.x - b.tx) < 1.5:
            b.state = 'drive'
            b.st = 0
    elif s == 'drive':
        d = -1 if PCX < b.x + 11 else 1
        b.face = d
        b.x += d * 0.4
        b.x = max(cam + 0.0, min(cam + 50.0, b.x))
        if b.st % (38 if fast else 52) == 18:
            mx, my, a = tank_aim(b)
            ebul(mx, my, a, 1.15)
            boom(mx, my, False)
        if b.st % (80 if fast else 110) == 70:
            mx, my, a = tank_aim(b)
            for o in (-0.18, 0.0, 0.18):
                ebul(mx, my, a + o, 1.0)
        if b.st >= (130 if fast else 170):
            b.state = 'rev'
            b.st = 0
    elif s == 'rev':
        b.jit = random.randint(-1, 1)
        if b.st % 3 == 0:
            boom(b.x + (21 if b.face < 0 else 0), b.y + 6, False)
        if b.st >= 28:
            b.dir = -1 if PCX < b.x + 11 else 1
            b.face = b.dir
            b.state = 'dash'
            b.st = 0
    elif s == 'dash':
        b.x += b.dir * 1.8
        if b.st % 3 == 0:
            boom(b.x + (22 if b.dir < 0 else 0), b.y + 8, False)
        shake(2)
        if b.x < cam - 26 or b.x > cam + 74:
            b.state = 'away'
            b.st = 0
    elif s == 'away':
        if b.st >= 35:
            if b.dir < 0:
                b.x = cam + 74.0
                b.tx = cam + 46.0
            else:
                b.x = cam - 24.0
                b.tx = cam + 4.0
            b.state = 'in'


# --- helicopter
def heli_next(b):
    ys = (6, 12, 18, 22)
    ny = ys[random.randint(0, 3)]
    for i in range(6):
        nx = cam + random.randint(10, 50)
        if ny < 17 or abs(nx + 11 - PCX) > 16:
            break
    b.tx = float(nx)
    b.ty = float(ny)
    b.state = 'move'
    b.st = 0


def upd_heli(b):
    b.st += 1
    b.fr += 1
    rage = b.hp < b.mhp * 0.4
    cx = b.x + 11
    if b.state == 'move':
        dx = b.tx - b.x
        dy = b.ty - b.y
        d = math.sqrt(dx * dx + dy * dy)
        sp = 1.6 if rage else 1.1
        if d < sp + 0.5:
            b.x = b.tx
            b.y = b.ty
            b.state = 'fire'
            b.st = 0
            b.pat = (b.pat + 1) % 4
        else:
            b.x += dx / d * sp
            b.y += dy / d * sp
        if b.st % 38 == 20:
            shoot_aimed(b.x + 3, b.y + 6, 1.1)
    else:
        st = b.st
        p = b.pat
        if p == 0:
            if st % 18 == 6 and st < 60:
                for o in (-0.3, 0.0, 0.3):
                    shoot_aimed(b.x + 3, b.y + 6, 1.1, o)
            dur = 66
        elif p == 1:
            if st == 8 or st == 38:
                for o in (-9, -3, 3, 9):
                    ebul(cx + o, b.y + 9, 1.5708, 1.1)
            dur = 56
        elif p == 2:
            if st % 4 == 0 and 6 <= st <= 54:
                ebul(cx, b.y + 8, 1.5708 + 1.0 * math.sin(st * 0.2), 1.0)
            dur = 60
        else:
            if st == 8:
                ring(cx, b.y + 6, 10, 0.9)
            if st == 38:
                ring(cx, b.y + 6, 10, 0.9, 0.31)
            dur = 56
        if rage:
            dur -= 14
        if b.st >= dur:
            heli_next(b)


# --- submarine
def upd_sub(b):
    b.st += 1
    s = b.state
    rage = b.hp < b.mhp * 0.4
    cx = b.x + 12
    if s == 'track':
        tgt = min(cam + 62.0, max(cam + 46.0, PCX))
        if abs(tgt - cx) > 1:
            b.x += 0.9 if tgt > cx else -0.9
        if b.st >= (40 if rage else 55):
            b.state = 'warn'
            b.st = 0
            c = b.x + 12
            b.cols = [min(cam + 70, max(cam + 36, v)) for v in (c - 12, c, c + 12)]
    elif s == 'warn':
        if b.st >= 26:
            for c in b.cols:
                if len(EB) < MAXEB:
                    EB.append([c, 33.0, 0.0, -2.4, 2, 10.0 + random.randint(0, 8)])
            b.state = 'rest'
            b.st = 0
            beep(200, 120)
    elif s == 'rest':
        if b.st == 20 and b.n % 2 == 1:
            for o in (-12, 0, 12):
                mortar(cx, 33.0, PCX + o)
        if b.st >= 40:
            b.n += 1
            b.st = 0
            if b.n >= (3 if rage else 2):
                b.n = 0
                b.state = 'rise'
            else:
                b.state = 'track'
    elif s == 'rise':
        b.y -= 0.4
        if b.y <= 26:
            b.y = 26.0
            b.state = 'up'
            b.st = 0
    elif s == 'up':
        if b.st % (38 if rage else 52) == 25:
            for o in (-0.35, 0.0, 0.35):
                shoot_aimed(b.x + 8, b.y - 5, 1.05, o)
        if b.st % 85 == 60 and len(EB) < MAXEB:
            EB.append([b.x, 30.0, -1.4, 0.0, 4, 0.0])
        if b.st >= (250 if rage else 210):
            b.state = 'sink'
    elif s == 'sink':
        b.y += 0.4
        if b.y >= 33:
            b.y = 33.0
            b.state = 'track'
            b.st = 0


# --- mech
def mech_shock(b, rage):
    cx = b.x + 7
    for v in (-1.5, 1.5):
        if len(EB) < MAXEB:
            EB.append([cx, 30.0, v, 0.0, 0, 0.0])
    if rage:
        for v in (-2.2, 2.2):
            if len(EB) < MAXEB:
                EB.append([cx, 30.0, v, 0.0, 0, 0.0])
        ring(cx, b.y + 10, 6, 0.8, 0.2)
    shake(8)
    beep(90, 120)


def mech_choose(b):
    dist = abs(PCX - (b.x + 7))
    r = random.randint(0, 99)
    b.st = 0
    if dist < 22 and r < 55:
        b.state = 'punch'
    elif r < 38:
        b.state = 'shoot'
    elif r < 78:
        b.state = 'crouch'
    else:
        b.state = 'shoot'
        b.pat = 1


def upd_mech(b):
    b.st += 1
    s = b.state
    cx = b.x + 7
    rage = b.hp < b.mhp * 0.45
    b.face = -1 if PCX < cx else 1
    if s == 'in' or s == 'air':
        b.vy += 0.28
        b.y += b.vy
        b.x += b.vx
        if s == 'air':
            b.x = max(cam + 0.0, min(cam + 58.0, b.x))
        if b.y >= GY - 24 and b.vy > 0:
            b.y = float(GY - 24)
            b.vy = 0.0
            b.vx = 0.0
            mech_shock(b, rage and s == 'air')
            b.state = 'idle'
            b.st = 0
    elif s == 'idle':
        d = PCX - cx
        if abs(d) > 30:
            b.x += 0.5 if d > 0 else -0.5
            b.fr += 1
        b.x = max(cam + 0.0, min(cam + 58.0, b.x))
        if b.st >= (20 if rage else 34):
            mech_choose(b)
    elif s == 'shoot':
        gap = 8 if rage else 11
        if b.pat == 1:
            if b.st == 10:
                for o in (-12, 0, 12):
                    mortar(cx, b.y + 4, PCX + o)
            if b.st >= 40:
                b.pat = 0
                b.state = 'idle'
                b.st = 0
        else:
            if b.st % gap == 6 and b.st < gap * 5:
                ax = cx + b.face * 6
                shoot_aimed(ax, b.y + 9, 1.2)
                if rage:
                    shoot_aimed(ax, b.y + 9, 1.0, 0.3)
            if b.st >= gap * 5 + 6:
                b.state = 'idle'
                b.st = 0
    elif s == 'crouch':
        if b.st >= 14:
            b.vx = max(-2.0, min(2.0, (PCX - cx + random.randint(-8, 8)) / 25.0))
            b.vy = -3.6
            b.state = 'air'
            b.st = 0
    elif s == 'punch':
        if b.st >= 22:
            b.state = 'idle'
            b.st = 0


def upd_boss():
    global BO, boss_done
    b = BO
    b.t += 1
    if b.flash:
        b.flash -= 1
    if b.dying:
        b.dying += 1
        if b.dying % 4 == 0:
            boom(b.x + random.randint(0, 20), b.y + random.randint(0, 10))
            shake(3)
        if b.dying >= 90:
            boss_done = True
            BO = None
            stage_clear()
        return
    if b.intro > 0:
        b.intro -= 1
        return
    if b.k == 0:
        upd_tank(b)
    elif b.k == 1:
        upd_heli(b)
    elif b.k == 2:
        upd_sub(b)
    else:
        upd_mech(b)
    if not P.dead:
        boss_contact()


# ------------------------------------------------------------ level / flow
def start_level(n):
    global level, LEN, THEME, WATER, PL, GMAP, SP, EN, EB, PB, FX, BO
    global boss_done, cam, CX, SHK, lvl_score, lvl_mult, lvl_rate
    level = n
    lv = LEVELS[n]
    LEN = lv[1]
    THEME = lv[2]
    WATER = lv[3]
    PL = [(a, b, GY) for a, b in lv[4]] + list(lv[5])
    GMAP = [0] * (LEN // 8 + 12)
    for a, b in lv[4]:
        for t in range(a // 8, b // 8):
            GMAP[t] = 1
    SP = list(lv[6])
    EN = []
    EB = []
    PB = []
    FX = []
    BO = None
    boss_done = False
    cam = 0.0
    CX = 0
    SHK = 0
    lvl_score = score
    lvl_mult = P.mult
    lvl_rate = P.rate
    reset_player()
    P.x = 8.0
    P.y = 0.0


def start_game(n):
    global score, mode, card_t
    score = 0
    P.lives = 3
    P.mult = 0
    P.rate = 0
    start_level(n)
    mode = "card"
    card_t = 0


def game_over():
    global mode, hi
    mode = "over"
    if score > hi:
        hi = score
    store_save()


def stage_clear():
    global mode, clear_t, score, maxlvl, hi
    mode = "clear"
    clear_t = 0
    score += 1000
    if level < 3:
        maxlvl = max(maxlvl, level + 1)
    if score > hi:
        hi = score
    store_save()


# ----------------------------------------------------------------- drawing
def draw_bg():
    c = CX
    th = THEME
    if th == 0:
        off = (c >> 1) % 44
        for j in range(3):
            x = j * 44 - off + 8
            for y in range(10, 32, 2):
                px(x, y)
            lineS(x - 4, 9, x + 5, 9)
            lineS(x - 2, 8, x + 3, 8)
    elif th == 1:
        off = (c * 2 // 5) % 40
        for j in range(3):
            x = j * 40 - off + 4
            h = 10 + ((j + (c * 2 // 5) // 40) * 7) % 9
            orect(x, 32 - h - 4, 14, h + 4)
            for wy in range(32 - h - 1, 29, 4):
                px(x + 3, wy)
                px(x + 8, wy)
    elif th == 2:
        off = (c >> 2) % 36
        for j in range(4):
            x = j * 36 - off
            lineS(x, 28, x + 9, 20)
            lineS(x + 9, 20, x + 18, 28)
        for x in range(0, 72, 3):
            px(x, 29)
    else:
        off = (c >> 1) % 24
        for y in (11, 17):
            for x in range(0, 72, 2):
                px(x, y)
        for j in range(4):
            x = j * 24 - off
            lineS(x, 11, x, 22)
            px(x + 1, 14)
            px(x + 1, 19)


def draw_terrain():
    c = CX
    t0 = c >> 3
    off = (t0 << 3) - c
    for i in range(10):
        ti = t0 + i
        sx = off + i * 8
        if ti < len(GMAP) and GMAP[ti]:
            D.blit(TILES[THEME], sx, GY, 8, 8, -1, 0, 0)
        elif WATER:
            D.blit(WAVE[(T >> 3) & 1], sx, GY, 8, 8, -1, 0, 0)
    for a, b, y in PL:
        if y < GY and b > c and a < c + 72:
            frect(a - c, y, b - a, 2)
            frect(a - c + 1, y + 2, 1, 1)
            frect(b - c - 2, y + 2, 1, 1)


def draw_enemy(e):
    sx = int(e.x - CX)
    sy = int(e.y)
    if sx < -12 or sx > 74:
        return
    k = e.k
    face = 1 if PCX > e.x + e.w / 2 else -1
    if k == RUN:
        dspr(SP_RUNNER[(e.t // 5) & 1], sx, sy, face)
    elif k == RIF:
        dspr(SP_RIF, sx, sy, face)
        a = aim_at(e.x + 2, e.y + 3)
        lineS(sx + 2 + math.cos(a) * 3, sy + 3 + math.sin(a) * 3,
              sx + 2 + math.cos(a) * 6, sy + 3 + math.sin(a) * 6)
    elif k == TUR:
        dspr(SP_TUR, sx, sy, 1)
        a = aim_at(e.x + 4, e.y + 2)
        if math.sin(a) > 0.2:
            a = 3.1416 if math.cos(a) < 0 else 0.0
        lineS(sx + 4, sy + 2, sx + 4 + math.cos(a) * 6, sy + 2 + math.sin(a) * 6)
    elif k == DRN:
        dspr(SP_DRN[(e.t >> 2) & 1], sx, sy, 1)
    elif k == CAP:
        dspr(SP_CAP, sx, sy, 1)
    elif k == LEP:
        if e.c:
            dspr(SP_LEP, sx, sy, face)
    elif k == PIK:
        frect(sx, sy, 7, 9, 0)
        orect(sx, sy, 7, 9)
        D.drawText(e.a, sx + 1, sy + 1, 1)
    if e.fl and k != PIK:
        orect(sx - 1, sy - 1, e.w + 2, e.h + 2)


def draw_player():
    if P.dead:
        return
    if P.inv and (T // 3) & 1:
        return
    sx = int(P.x - CX)
    if P.prone:
        dspr(SP_PRONE, sx - 1, int(P.y) - 4, P.face)
        cy = P.y - 2.0
    elif not P.gr:
        dspr(SP_JUMP, sx, int(P.y) - 6, P.face)
        cy = P.y - 3.0
    else:
        moving = P.an and (thumby.buttonL.pressed() or thumby.buttonR.pressed())
        if moving:
            s = SP_RUN1 if (T // 4) & 1 else SP_RUN2
        else:
            s = SP_STAND
        dspr(s, sx, int(P.y) - 8, P.face)
        cy = P.y - 5.0
    cx = sx + 2.5
    lineS(cx + P.ax * 3, cy + P.ay * 3, cx + P.ax * 6, cy + P.ay * 6)


def draw_bullets():
    for b in PB:
        x = b[0] - CX
        px(x, b[1])
        px(x - b[2] * 0.3, b[1] - b[3] * 0.3)
    for b in EB:
        x = int(b[0] - CX)
        y = int(b[1])
        k = b[4]
        if k == 2:
            frect(x - 1, y - 2, 2, 4)
            px(x, y + 3)
        elif k == 4:
            frect(x - 3, y - 1, 6, 2)
        else:
            px(x, y - 1)
            px(x - 1, y)
            px(x + 1, y)
            px(x, y + 1)


def draw_fx():
    for f in FX:
        x = f[0] - CX
        y = f[1]
        t = f[2]
        r = t // 2 + 1
        if f[3] > 6 and t < 4:
            frect(x - 1, y - 1, 3, 3)
        for d in D8:
            px(x + d[0] * r, y + d[1] * r)


def draw_hud():
    for i in range(P.lives):
        frect(1 + i * 5, 1, 3, 5)
    D.drawText("M%dR%d" % (P.mult + 1, P.rate + 1), 16, 0, 1)
    s = str(score)
    D.drawText(s, 72 - len(s) * 6, 0, 1)
    if BO is not None and BO.intro == 0 and not BO.dying:
        w = int(40 * BO.hp / BO.mhp)
        frect(16, 8, 40, 1, 0)
        frect(16, 8, w, 1)
        px(15, 8)
        px(56, 8)


def draw_tank(b):
    sx = int(b.x - CX) + b.jit
    sy = int(b.y)
    dbig(SP_TANK, sx, sy, b.face < 0)
    mx, my, a = tank_aim(b)
    cx = sx + 11
    cy = sy + 2
    lineS(cx, cy, mx - CX + b.jit, my)
    lineS(cx, cy + 1, mx - CX + b.jit, my + 1)
    if b.state == 'rev' or b.state == 'dash':
        for i in range(3):
            px(sx + (23 if b.face < 0 else -2) + (T % 3), sy + 4 + i * 2)


def draw_heli(b):
    sx = int(b.x - CX)
    sy = int(b.y)
    dbig(SP_HELI, sx, sy, True)
    if (b.fr >> 1) & 1:
        lineS(sx - 2, sy, sx + 22, sy)
    else:
        lineS(sx + 3, sy, sx + 19, sy)
        px(sx - 2, sy)
        px(sx + 23, sy)
    if (b.fr >> 1) & 1:
        px(sx + 21, sy + 3)
        px(sx + 21, sy + 4)


def draw_sub(b):
    sx = int(b.x - CX)
    sy = int(b.y)
    if b.state == 'track' or b.state == 'warn' or b.state == 'rest':
        dbig(SP_HULLD, sx, 33, True)
        if b.state == 'warn':
            for c in b.cols:
                cx = int(c - CX)
                frect(cx - 2, 32, 5, 1)
                px(cx, 38 - (T % 8))
                px(cx + 2, 36 - (T % 6))
                px(cx - 2, 35 - (T % 5))
        return
    dbig(SP_HULL, sx, sy, True)
    if sy < 31:
        dbig(SP_TOWER, sx + 6, sy - 7, True)
    # water covers everything below the waterline
    wt = int(b.x - 2) >> 3
    frect((wt << 3) - CX, GY, 40, 8, 0)
    for i in range(5):
        D.blit(WAVE[(T >> 3) & 1], ((wt + i) << 3) - CX, GY, 8, 8, -1, 0, 0)


def draw_mech(b):
    sx = int(b.x - CX)
    sy = int(b.y)
    s = b.state
    if s == 'air' or s == 'in':
        fr = 2
    elif s == 'crouch':
        fr = 2
        sy += 3
    elif s == 'idle':
        fr = (b.fr >> 3) & 1
    else:
        fr = 0
    dbig(SP_MECH[fr], sx, sy, b.face < 0)
    cx = sx + 7
    if s == 'punch':
        if b.st < 12:
            lineS(cx + b.face * 5, sy + 6, cx + b.face * 5, sy)
        else:
            frect(cx + b.face * 5 - (13 if b.face < 0 else 0), sy + 7, 13, 3)
    elif s == 'shoot' and b.pat == 0:
        a = aim_at(b.x + 7, sy + 9)
        lineS(cx + b.face * 5, sy + 9, cx + b.face * 5 + math.cos(a) * 6,
              sy + 9 + math.sin(a) * 6)
    else:
        lineS(cx + b.face * 5, sy + 9, cx + b.face * 11, sy + 9)


def draw_boss():
    b = BO
    if b.k == 0:
        draw_tank(b)
    elif b.k == 1:
        draw_heli(b)
    elif b.k == 2:
        draw_sub(b)
    else:
        draw_mech(b)
    if b.flash:
        bx = boss_box()
        if bx is not None:
            orect(bx[0] - CX - 1, bx[1] - 1, bx[2] - bx[0] + 2, bx[3] - bx[1] + 2)


def draw_play():
    draw_bg()
    draw_terrain()
    for e in EN:
        draw_enemy(e)
    if BO is not None and BO.intro == 0:
        draw_boss()
    draw_bullets()
    draw_player()
    draw_fx()
    draw_hud()
    if BO is not None and BO.intro > 0 and (T >> 3) & 1:
        center("WARNING", 15)


# -------------------------------------------------------------- mode steps
def play_step():
    global cam, CX, BO, SHK
    update_player()
    if BO is None and not boss_done:
        spawn_check()
    update_enemies()
    update_pbul()
    hit_pbul()
    update_ebul()
    update_fx()
    if BO is not None:
        upd_boss()
    if mode != "play":
        return
    tgt = min(LEN - 72, max(cam, P.x - 28))
    if tgt > cam:
        cam = float(int(tgt))
    if BO is None and not boss_done and cam >= LEN - 72:
        BO = new_boss(level)
    CX = int(cam)
    if SHK > 0:
        SHK -= 1
        CX += random.randint(-1, 1)
    draw_play()


def title_step():
    global sel_lvl
    center("IRONFIRE", 1)
    center("< STAGE %d >" % (sel_lvl + 1), 12)
    center("A: START", 22)
    frect(0, 39, 72, 1)
    dspr(SP_STAND, 6, 31, 1)
    lineS(10, 34, 15, 34)
    px(19 + (T % 12), 34)
    dbig(SP_TANK, 44, 28, True)
    if thumby.buttonL.justPressed():
        sel_lvl = max(0, sel_lvl - 1)
    if thumby.buttonR.justPressed():
        sel_lvl = min(maxlvl, sel_lvl + 1)
    if thumby.buttonA.justPressed():
        start_game(sel_lvl)


def card_step():
    global card_t, mode
    card_t += 1
    center("STAGE %d" % (level + 1), 4)
    center(LEVELS[level][0], 14)
    D.drawText("A JUMP", 18, 24, 1)
    D.drawText("B FIRE", 18, 32, 1)
    if card_t >= 80 or thumby.buttonA.justPressed() and card_t > 20:
        mode = "play"


def clear_step():
    global clear_t, mode, card_t
    clear_t += 1
    center("STAGE CLEAR", 6)
    center("BONUS 1000", 16)
    center(str(score), 26)
    if clear_t >= 120:
        if level >= 3:
            mode = "win"
        else:
            start_level(level + 1)
            mode = "card"
            card_t = 0


def over_step():
    global mode, score, card_t
    center("GAME OVER", 2)
    center("SCORE", 12)
    center(str(score), 20)
    center("HI " + str(hi), 28)
    if thumby.buttonA.justPressed():
        score = lvl_score
        P.lives = 3
        P.mult = lvl_mult
        P.rate = lvl_rate
        start_level(level)
        mode = "card"
        card_t = 0


def win_step():
    global mode
    center("MISSION", 4)
    center("COMPLETE", 13)
    center(str(score), 23)
    center("A: TITLE", 32)
    if thumby.buttonA.justPressed():
        mode = "title"


def main():
    global T
    load_save()
    while True:
        T += 1
        D.fill(0)
        if mode == "title":
            title_step()
        elif mode == "card":
            card_step()
        elif mode == "play":
            play_step()
        elif mode == "clear":
            clear_step()
        elif mode == "over":
            over_step()
        else:
            win_step()
        D.update()


main()