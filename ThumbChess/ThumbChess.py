# CHESS QUEST - chess with little walking, fighting pieces (Thumby / MicroPython)
# You are WHITE (bottom). D-pad: move cursor. A: select / move. B: cancel.
# Hold B (when nothing is selected) to return to the menu.
# Difficulty: EASY = random moves, MEDIUM = takes a piece if it can, else random,
#             HARD = looks ahead and tries to win a piece by force.
# Full chess rules: check, checkmate, stalemate, castling, en passant, promotion
# (pawns promote to a queen), 50-move rule, insufficient material.

import thumby
import random
import time

D = thumby.display
D.setFPS(30)

# ------------------------------------------------------------------ sprites
# 8x8 art facing right. # = body, o = detail, . = empty
ART = {
    1: ("........", "..###...", ".#####.#", ".##o##.#",
        ".#####.#", "..###..#", ".#####.#", ".##.##.."),
    2: ("..#.#...", ".######.", ".##o###.", ".#######",
        "..######", "..####..", ".#####..", ".######."),
    3: ("...##...", "..####..", "..#o##..", "..####..",
        "...##...", ".######.", ".######.", "########"),
    4: ("##.##.##", "########", ".######.", ".##oo##.",
        ".######.", ".######.", ".######.", "########"),
    5: ("#.#.#.#.", "#######.", ".#####..", "..#o#...",
        "..###...", ".#####..", "#######.", "########"),
    6: ("...#....", "..###...", "...#....", ".#####..",
        ".##o##..", ".#####..", "#######.", "########"),
}


def build(art, black):
    bm = bytearray(8)
    mk = bytearray(8)
    for x in range(8):
        for y in range(8):
            if art[y][x] != '.':
                edge = (x == 0 or x == 7 or y == 0 or y == 7 or
                        art[y][x - 1] == '.' or art[y][x + 1] == '.' or
                        art[y - 1][x] == '.' or art[y + 1][x] == '.')
                det = art[y][x] == 'o'
                if black:
                    on = edge or det
                else:
                    on = edge or not det
                if on:
                    bm[x] |= 1 << y
                mk[x] |= 1 << y
    return bm, mk


def flip(b):
    return bytearray([b[7 - i] for i in range(8)])


SPR = {}
for _ty in ART:
    _row = []
    for _bl in (False, True):
        _bm, _mk = build(ART[_ty], _bl)
        _row.append((_bm, _mk))
        _row.append((flip(_bm), flip(_mk)))
    SPR[_ty] = _row

DARK = bytearray([0x55, 0xAA, 0x55, 0xAA, 0x55, 0xAA, 0x55, 0xAA])


def draw_piece(code, x, y, mir):
    e = SPR[abs(code)][(2 if code < 0 else 0) + mir]
    D.blitWithMask(e[0], int(x), int(y), 8, 8, -1, 0, 0, e[1])


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


def beep(f, ms):
    try:
        thumby.audio.play(f, ms)
    except Exception:
        pass


# ------------------------------------------------------------- chess engine
# board[0] = a8 ... board[63] = h1.  White positive, black negative.
# 1 pawn, 2 knight, 3 bishop, 4 rook, 5 queen, 6 king
board = [0] * 64
ep = -1
cr = 15          # castling rights: 1 wK, 2 wQ, 4 bK, 8 bQ
hm = 0           # half-move clock for 50 move rule
VAL = (0, 100, 320, 330, 500, 900, 0)
BACK = (4, 2, 3, 5, 6, 3, 2, 4)

CRM = [15] * 64
CRM[60] = 12
CRM[63] = 14
CRM[56] = 13
CRM[4] = 3
CRM[7] = 11
CRM[0] = 7

DIRS = ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1))
KN = [[] for _ in range(64)]
KG = [[] for _ in range(64)]
RAYS = [[] for _ in range(64)]
PA = [[[] for _ in range(64)], [[] for _ in range(64)]]
CEN = [0] * 64
for _r in range(8):
    for _c in range(8):
        _s = _r * 8 + _c
        CEN[_s] = 3 - ((abs(2 * _r - 7) + abs(2 * _c - 7)) >> 2)
        for _dr, _dc in ((1, 2), (2, 1), (-1, 2), (-2, 1),
                         (1, -2), (2, -1), (-1, -2), (-2, -1)):
            _rr = _r + _dr
            _cc = _c + _dc
            if 0 <= _rr < 8 and 0 <= _cc < 8:
                KN[_s].append(_rr * 8 + _cc)
        for _dr, _dc in DIRS:
            _rr = _r + _dr
            _cc = _c + _dc
            if 0 <= _rr < 8 and 0 <= _cc < 8:
                KG[_s].append(_rr * 8 + _cc)
            _ray = []
            while 0 <= _rr < 8 and 0 <= _cc < 8:
                _ray.append(_rr * 8 + _cc)
                _rr += _dr
                _cc += _dc
            RAYS[_s].append(_ray)
        for _dc in (-1, 1):
            if 0 <= _c + _dc < 8:
                if _r + 1 < 8:      # a white pawn sitting below attacks upward
                    PA[1][_s].append((_r + 1) * 8 + _c + _dc)
                if _r - 1 >= 0:     # a black pawn sitting above attacks downward
                    PA[0][_s].append((_r - 1) * 8 + _c + _dc)


def reset_board():
    global ep, cr, hm
    for i in range(64):
        board[i] = 0
    for c in range(8):
        board[c] = -BACK[c]
        board[8 + c] = -1
        board[48 + c] = 1
        board[56 + c] = BACK[c]
    ep = -1
    cr = 15
    hm = 0


def attacked(s, by):
    b = board
    for t in PA[(by + 1) >> 1][s]:
        if b[t] == by:
            return True
    n = 2 * by
    for t in KN[s]:
        if b[t] == n:
            return True
    k = 6 * by
    for t in KG[s]:
        if b[t] == k:
            return True
    rk = 4 * by
    qn = 5 * by
    bs = 3 * by
    rays = RAYS[s]
    for d in range(4):
        for t in rays[d]:
            p = b[t]
            if p:
                if p == rk or p == qn:
                    return True
                break
    for d in range(4, 8):
        for t in rays[d]:
            p = b[t]
            if p:
                if p == bs or p == qn:
                    return True
                break
    return False


def gen(c, caps=False):
    mv = []
    b = board
    for s in range(64):
        p = b[s]
        if p * c <= 0:
            continue
        t = p * c
        if t == 1:
            r = s >> 3
            col = s & 7
            fwd = -8 * c
            to = s + fwd
            if c == 1:
                last = (r == 1)
                start = (r == 6)
            else:
                last = (r == 6)
                start = (r == 1)
            for dc in (-1, 1):
                cc = col + dc
                if 0 <= cc < 8:
                    d = to + dc
                    q = b[d]
                    if q * c < 0:
                        mv.append((s, d, 5 if last else 0))
                    elif d == ep:
                        mv.append((s, d, 2))
            if not caps and b[to] == 0:
                mv.append((s, to, 5 if last else 0))
                if start and b[to + fwd] == 0:
                    mv.append((s, to + fwd, 1))
        elif t == 2:
            for d in KN[s]:
                q = b[d]
                if q * c < 0 or (q == 0 and not caps):
                    mv.append((s, d, 0))
        elif t == 6:
            for d in KG[s]:
                q = b[d]
                if q * c < 0 or (q == 0 and not caps):
                    mv.append((s, d, 0))
            if not caps:
                home = 60 if c == 1 else 4
                if s == home:
                    rk = 1 if c == 1 else 4
                    rq = 2 if c == 1 else 8
                    if (cr & (rk | rq)) and not attacked(s, -c):
                        if (cr & rk) and b[s + 1] == 0 and b[s + 2] == 0 \
                                and b[s + 3] == 4 * c \
                                and not attacked(s + 1, -c) \
                                and not attacked(s + 2, -c):
                            mv.append((s, s + 2, 3))
                        if (cr & rq) and b[s - 1] == 0 and b[s - 2] == 0 \
                                and b[s - 3] == 0 and b[s - 4] == 4 * c \
                                and not attacked(s - 1, -c) \
                                and not attacked(s - 2, -c):
                            mv.append((s, s - 2, 4))
        else:
            if t == 3:
                lo = 4
                hi = 8
            elif t == 4:
                lo = 0
                hi = 4
            else:
                lo = 0
                hi = 8
            rays = RAYS[s]
            for d in range(lo, hi):
                for x in rays[d]:
                    q = b[x]
                    if q == 0:
                        if not caps:
                            mv.append((s, x, 0))
                    else:
                        if q * c < 0:
                            mv.append((s, x, 0))
                        break
    return mv


def make(m):
    global ep, cr
    f, t, fl = m
    p = board[f]
    cap = board[t]
    old_ep = ep
    old_cr = cr
    board[t] = p
    board[f] = 0
    if fl == 1:
        ep = (f + t) >> 1
    else:
        ep = -1
    if fl == 2:
        cs = t + 8 if p > 0 else t - 8
        cap = board[cs]
        board[cs] = 0
    elif fl == 3:
        board[f + 1] = board[f + 3]
        board[f + 3] = 0
    elif fl == 4:
        board[f - 1] = board[f - 4]
        board[f - 4] = 0
    elif fl == 5:
        board[t] = 5 if p > 0 else -5
    cr &= CRM[f] & CRM[t]
    return (cap, old_ep, old_cr)


def unmake(m, u):
    global ep, cr
    f, t, fl = m
    cap, ep, cr = u
    p = board[t]
    if fl == 5:
        p = 1 if p > 0 else -1
    board[f] = p
    if fl == 2:
        board[t] = 0
        board[t + 8 if p > 0 else t - 8] = cap
    else:
        board[t] = cap
        if fl == 3:
            board[f + 3] = board[f + 1]
            board[f + 1] = 0
        elif fl == 4:
            board[f - 4] = board[f - 1]
            board[f - 1] = 0


def legal(c):
    out = []
    for m in gen(c):
        u = make(m)
        if not attacked(board.index(6 * c), -c):
            out.append(m)
        unmake(m, u)
    return out


def insufficient():
    n = 0
    for p in board:
        if p and abs(p) != 6:
            if abs(p) in (1, 4, 5):
                return False
            n += 1
    return n <= 1


# ---------------------------------------------------------------------- AI
ai_move = None
last_ai = (-1, -1)
JIT = 6


def is_cap(m):
    return board[m[1]] != 0 or m[2] == 2


def ai_pick(moves):
    # EASY: random.  MEDIUM: biggest capture if any, otherwise random.
    if diff == 0:
        return moves[random.randint(0, len(moves) - 1)]
    best = []
    bv = -1
    for m in moves:
        if is_cap(m):
            v = 100 if m[2] == 2 else VAL[abs(board[m[1]])]
            if v > bv:
                bv = v
                best = [m]
            elif v == bv:
                best.append(m)
    if best:
        return best[random.randint(0, len(best) - 1)]
    return moves[random.randint(0, len(moves) - 1)]


def material_black():
    s = 0
    for p in board:
        if p:
            v = VAL[abs(p)]
            if p < 0:
                s += v
            else:
                s -= v
    return s


def gain_black():
    # best net material black can win with one capture right now
    best = 0
    for m in gen(-1, True):
        f, t, fl = m
        if fl == 2:
            v = 100
        else:
            v = VAL[abs(board[t])]
        if fl == 5:
            v += 800
        if attacked(t, 1):
            if abs(board[f]) == 6:
                continue
            v -= VAL[abs(board[f])]
        if v > best:
            best = v
    return best


def bonus(m):
    f, t, fl = m
    ty = -board[f]
    b = 0
    if ty == 2 or ty == 3:
        b = 5 * (CEN[t] - CEN[f])
    elif ty == 1:
        b = 3 * ((t >> 3) - (f >> 3))
    elif ty == 5:
        b = CEN[t] - CEN[f]
    if fl == 3 or fl == 4:
        b += 15
    elif ty == 6:
        b -= 8
    if (f, t) == (last_ai[1], last_ai[0]):
        b -= 10
    return b


def hard_gen(moves):
    # Depth-2 search (our move, every reply) with a "what can we grab next"
    # leaf score. A move scores high when, whatever White answers, Black is
    # left with a capture that wins material -> White is forced to lose a piece.
    global ai_move
    t0 = time.ticks_ms()
    cand = [m for m in moves if is_cap(m)] + [m for m in moves if not is_cap(m)]
    best = None
    bs = -10 ** 9
    n = 0
    for m in cand:
        if best is not None and time.ticks_diff(time.ticks_ms(), t0) > 9000:
            break
        u = make(m)
        wm = legal(1)
        if not wm:
            sc = 100000 if attacked(board.index(6), -1) else 0
        else:
            mat = material_black()
            sc = 10 ** 9
            for r in [x for x in wm if is_cap(x)] + [x for x in wm if not is_cap(x)]:
                if r[2] == 2:
                    adj = 100
                else:
                    adj = VAL[abs(board[r[1]])]
                if r[2] == 5:
                    adj += 800
                u2 = make(r)
                if attacked(board.index(-6), 1) and not legal(-1):
                    v = -100000
                else:
                    v = mat - adj + gain_black()
                unmake(r, u2)
                if v < sc:
                    sc = v
                if sc < bs - JIT:
                    break
                n += 1
                if n & 7 == 0:
                    yield
        unmake(m, u)
        sc += bonus(m) + random.randint(0, JIT)
        if sc > bs:
            bs = sc
            best = m
        yield
    ai_move = best


# --------------------------------------------------------------- animation
ACT = []     # actors: [code, x, y, mirror, lift, visible]
HIDE = []    # board squares not drawn while an actor stands in for them
FX = []      # effects: ('p',x,y) ('l',x0,y0,x1,y1) ('r',x,y,w,h)
SH = [0, 0]  # screen shake [frames, magnitude]
D8 = ((1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1))
D4 = ((1, 0), (0, 1), (-1, 0), (0, -1))
# speed px/frame, style (0 walk-bob, 1 hop, 2 float), bob period
STYLE = {1: (1.3, 0, 3), 2: (0.9, 1, 0), 3: (2.0, 2, 0),
         4: (1.5, 0, 5), 5: (2.6, 0, 2), 6: (1.0, 0, 6)}


def sgn(v):
    if v > 0:
        return 1
    if v < 0:
        return -1
    return 0


def ring(cx, cy, r):
    return [('p', cx + d[0] * r, cy + d[1] * r) for d in D8]


def slide(a, x1, y1, ty, hop=7):
    spd, kind, per = STYLE[ty]
    x0 = a[1]
    y0 = a[2]
    dist = max(abs(x1 - x0), abs(y1 - y0))
    if dist >= 1:
        n = max(4, int(dist / spd))
        if x1 != x0:
            a[3] = 1 if x1 < x0 else 0
        for i in range(1, n + 1):
            p = i / n
            a[1] = x0 + (x1 - x0) * p
            a[2] = y0 + (y1 - y0) * p
            if kind == 1:
                a[4] = hop * 4 * p * (1 - p)
            elif kind == 2:
                a[4] = 2 + ((i // 4) & 1)
            else:
                a[4] = (i // per) & 1
            yield
    a[4] = 0


def die(v):
    for i in range(10):
        v[5] = 1 if (i // 2) % 2 == 0 else 0
        yield
    v[5] = 0
    cx = v[1] + 4
    cy = v[2] + 4
    for i in range(1, 9):
        FX[:] = [('p', cx + d[0] * i, cy + d[1] * i) for d in D8]
        yield
    FX[:] = []


def atk_pawn(a, v, dx, dy):
    # two quick spear thrusts
    for k in range(2):
        for i in range(4):
            a[1] += dx
            a[2] += dy
            yield
        cx = v[1] + 4 - dx * 2
        cy = v[2] + 4 - dy * 2
        FX[:] = [('p', cx + d[0] * 2, cy + d[1] * 2) for d in D4]
        beep(300, 30)
        v[5] = 0
        yield
        v[5] = 1
        yield
        FX[:] = []
        for i in range(4):
            a[1] -= dx
            a[2] -= dy
            yield


def atk_knight(a, v):
    # already hopped onto the victim: stomp
    SH[0] = 5
    SH[1] = 2
    beep(200, 80)
    for r in range(1, 6):
        FX[:] = ring(a[1] + 4, a[2] + 7, r * 2)
        v[5] = r & 1
        yield
    v[5] = 1
    FX[:] = []


def atk_bishop(a, v, dx, dy):
    # ranged: charge up, fire an orb along the diagonal
    cx = a[1] + 4
    cy = a[2] + 4
    if dx:
        a[3] = 1 if dx < 0 else 0
    for i in range(16):
        a[4] = 2 + ((i // 3) & 1)
        k = i % 8
        k2 = (k + 4) % 8
        FX[:] = [('p', cx + D8[k][0] * 6, cy + D8[k][1] * 6),
                 ('p', cx + D8[k2][0] * 6, cy + D8[k2][1] * 6)]
        yield
    tx = v[1] + 4
    ty = v[2] + 4
    dist = max(abs(tx - cx), abs(ty - cy))
    n = max(4, int(dist / 3))
    beep(700, 60)
    for i in range(1, n + 1):
        ox = cx + (tx - cx) * i / n
        oy = cy + (ty - cy) * i / n
        FX[:] = [('r', ox - 1, oy - 1, 3, 3), ('p', ox - dx * 3, oy - dy * 3),
                 ('p', ox - dx * 5, oy - dy * 5)]
        yield
    a[4] = 0
    beep(900, 60)
    for r in range(1, 7):
        FX[:] = ring(tx, ty, r) + ring(tx, ty, max(0, r - 2))
        v[5] = r & 1
        yield
    v[5] = 1
    FX[:] = []


def atk_rook(a, v, dx, dy):
    # wind up backwards, then charge like a battering ram
    for i in range(8):
        a[1] -= dx * 0.7
        a[2] -= dy * 0.7
        yield
    for i in range(4):
        FX[:] = [('p', a[1] + (i & 1) * 7, a[2] + 7)]
        yield
    for i in range(12):
        if max(abs(v[1] - a[1]), abs(v[2] - a[2])) <= 3:
            break
        a[1] += dx * 3.5
        a[2] += dy * 3.5
        FX[:] = [('p', a[1] - dx * 4, a[2] + 7), ('p', a[1] - dx * 7, a[2] + 6),
                 ('p', a[1] - dy * 4, a[2] + 7)]
        yield
    SH[0] = 7
    SH[1] = 2
    beep(150, 100)
    cx = v[1] + 4
    cy = v[2] + 4
    for i in range(8):
        v[1] += dx * 0.8
        v[2] += dy * 0.8
        v[5] = i & 1
        FX[:] = [('l', cx, cy, cx + D8[k][0] * (i + 2), cy + D8[k][1] * (i + 2))
                 for k in (0, 2, 4, 6)]
        yield
    v[5] = 1
    FX[:] = []


def atk_queen(a, v, dx, dy):
    # whirling spin, then a double slash
    cx = a[1] + 4
    cy = a[2] + 4
    for i in range(14):
        a[3] = i & 1
        a[4] = 1 + ((i // 2) & 1)
        k = (i * 3) % 8
        k2 = (k + 4) % 8
        FX[:] = [('l', cx, cy, cx + D8[k][0] * 5, cy + D8[k][1] * 5),
                 ('l', cx, cy, cx + D8[k2][0] * 5, cy + D8[k2][1] * 5)]
        yield
    a[4] = 0
    a[3] = 1 if dx < 0 else 0
    beep(1200, 50)
    vx = v[1]
    vy = v[2]
    for i in range(3):
        FX[:] = [('l', vx, vy, vx + 7, vy + 7)]
        v[5] = 0
        yield
        yield
        FX[:] = [('l', vx + 7, vy, vx, vy + 7)]
        v[5] = 1
        yield
        yield
    FX[:] = []


def atk_king(a, v, dx, dy):
    # slow, heavy: rise up, pause, SLAM
    for i in range(12):
        a[4] = (i + 1) // 2
        yield
    for i in range(6):
        yield
    a[4] = 0
    for i in range(3):
        a[1] += dx
        a[2] += dy
        yield
    SH[0] = 9
    SH[1] = 3
    beep(100, 160)
    cx = a[1] + 4
    gy = a[2] + 7
    for i in range(1, 9):
        FX[:] = [('l', cx - i * 3, gy, cx - i * 3 - 2, gy),
                 ('l', cx + i * 3, gy, cx + i * 3 + 2, gy)]
        v[5] = i & 1
        yield
    v[5] = 1
    FX[:] = []
    for i in range(3):
        a[1] -= dx
        a[2] -= dy
        yield


def play(m, p, vcode, vsq):
    f, t, fl = m
    ty = abs(p)
    x1 = (t & 7) * 8
    y1 = (t >> 3) * 8
    a = [p, (f & 7) * 8, (f >> 3) * 8, 0 if p > 0 else 1, 0, 1]
    ACT[:] = [a]
    HIDE[:] = [t]
    FX[:] = []
    rk = None
    rdx = 0
    rdy = 0
    if fl == 3 or fl == 4:
        if fl == 3:
            src = f + 3
            dst = f + 1
        else:
            src = f - 4
            dst = f - 1
        rk = [board[dst], (src & 7) * 8, (src >> 3) * 8, 0 if board[dst] > 0 else 1, 0, 1]
        rdx = (dst & 7) * 8
        rdy = (dst >> 3) * 8
        ACT.append(rk)
        HIDE.append(dst)
    if vcode:
        v = [vcode, (vsq & 7) * 8, (vsq >> 3) * 8, 0 if vcode > 0 else 1, 0, 1]
        ACT.append(v)
        dx = sgn(v[1] - a[1])
        dy = sgn(v[2] - a[2])
        if dx:
            a[3] = 1 if dx < 0 else 0
        if ty == 2:
            yield from slide(a, v[1], v[2], 2, 10)
            yield from atk_knight(a, v)
        elif ty == 3:
            yield from atk_bishop(a, v, dx, dy)
        else:
            sx = v[1] - dx * 8
            sy = v[2] - dy * 8
            if sx != a[1] or sy != a[2]:
                yield from slide(a, sx, sy, ty)
            if ty == 1:
                yield from atk_pawn(a, v, dx, dy)
            elif ty == 4:
                yield from atk_rook(a, v, dx, dy)
            elif ty == 5:
                yield from atk_queen(a, v, dx, dy)
            else:
                yield from atk_king(a, v, dx, dy)
        yield from die(v)
        ACT.remove(v)
        yield from slide(a, x1, y1, ty)
    else:
        yield from slide(a, x1, y1, ty, 7)
    if rk is not None:
        yield from slide(rk, rdx, rdy, 4)
    if fl == 5:
        a[0] = 5 if p > 0 else -5
        beep(1000, 100)
        for r in range(1, 7):
            FX[:] = ring(x1 + 4, y1 + 4, r + 2)
            yield
        FX[:] = []


# ---------------------------------------------------------------- game state
mode = "menu"
diff = 1
turn = 1
cur_r = 6
cur_c = 4
sel = -1
sel_moves = []
cur_moves = []
cam = 24.0
anim = None
snap = None
think_gen = None
think_t = 0
think_moves = []
check_flag = False
res1 = ""
res2 = ""
bhold = 0
T = 0
hold = [0, 0, 0, 0]


def start_game():
    global turn, cur_r, cur_c, sel, sel_moves, cam, mode, cur_moves
    global check_flag, last_ai, bhold
    reset_board()
    turn = 1
    cur_r = 6
    cur_c = 4
    sel = -1
    sel_moves = []
    cam = 24.0
    check_flag = False
    last_ai = (-1, -1)
    bhold = 0
    ACT[:] = []
    HIDE[:] = []
    FX[:] = []
    cur_moves = legal(1)
    mode = "player"


def start_move(m):
    global anim, turn, hm, mode, last_ai
    f, t, fl = m
    p = board[f]
    vcode = board[t]
    vsq = t
    if fl == 2:
        vsq = t + 8 if p > 0 else t - 8
        vcode = board[vsq]
    if abs(p) == 1 or vcode:
        hm = 0
    else:
        hm += 1
    if p < 0:
        last_ai = (f, t)
    make(m)
    anim = play(m, p, vcode, vsq)
    turn = -turn
    mode = "anim"


def after_anim():
    global mode, check_flag, res1, res2, cur_moves, sel, sel_moves
    global think_gen, think_t, think_moves, snap
    ACT[:] = []
    HIDE[:] = []
    FX[:] = []
    moves = legal(turn)
    check_flag = attacked(board.index(6 * turn), -turn)
    if not moves:
        mode = "over"
        if check_flag:
            res1 = "CHECKMATE"
            res2 = "YOU WIN!" if turn == -1 else "YOU LOSE"
        else:
            res1 = "STALEMATE"
            res2 = "DRAW"
    elif hm >= 100 or insufficient():
        mode = "over"
        res1 = "DRAW"
        res2 = ""
    elif turn == 1:
        cur_moves = moves
        sel = -1
        sel_moves = []
        mode = "player"
    else:
        think_moves = moves
        think_t = 0
        mode = "think"
        if diff == 2:
            snap = list(board)
            think_gen = hard_gen(moves)
        else:
            think_gen = None


def think_step():
    global think_gen, think_t
    think_t += 1
    if think_gen is None:
        if think_t >= 14:
            start_move(ai_pick(think_moves))
        return
    try:
        next(think_gen)
    except StopIteration:
        think_gen = None
        mv = ai_move
        if mv is None:
            mv = think_moves[random.randint(0, len(think_moves) - 1)]
        start_move(mv)


def nav():
    global cur_r, cur_c
    bs = (thumby.buttonU, thumby.buttonD, thumby.buttonL, thumby.buttonR)
    dr = (-1, 1, 0, 0)
    dc = (0, 0, -1, 1)
    for i in range(4):
        if bs[i].pressed():
            hold[i] += 1
            h = hold[i]
            if h == 1 or (h > 10 and h % 3 == 0):
                cur_r = min(7, max(0, cur_r + dr[i]))
                cur_c = min(7, max(0, cur_c + dc[i]))
        else:
            hold[i] = 0


def player_step():
    global sel, sel_moves, mode, bhold
    nav()
    if thumby.buttonA.justPressed():
        s = cur_r * 8 + cur_c
        if sel >= 0:
            for m in sel_moves:
                if m[1] == s:
                    sel = -1
                    sel_moves = []
                    start_move(m)
                    return
        sel = -1
        sel_moves = []
        if board[s] > 0:
            ms = [m for m in cur_moves if m[0] == s]
            if ms:
                sel = s
                sel_moves = ms
    if thumby.buttonB.justPressed():
        sel = -1
        sel_moves = []
    if thumby.buttonB.pressed():
        bhold += 1
        if bhold >= 45 and sel < 0:
            mode = "menu"
    else:
        bhold = 0


def anim_step():
    try:
        next(anim)
    except StopIteration:
        after_anim()


# ------------------------------------------------------------------ drawing
def draw_scene(b, cy):
    ox = 0
    oy = 0
    if SH[0] > 0:
        ox = random.randint(-SH[1], SH[1])
        oy = random.randint(-SH[1], SH[1])
        SH[0] -= 1
    r0 = max(0, cy // 8)
    r1 = min(7, (cy + 39) // 8)
    for r in range(r0, r1 + 1):
        y = r * 8 - cy + oy
        for c in range(8):
            x = c * 8 + ox
            if (r + c) & 1:
                D.blit(DARK, x, y, 8, 8, -1, 0, 0)
            s = r * 8 + c
            p = b[s]
            if p and s not in HIDE:
                yy = y
                if s == sel and (T // 6) & 1:
                    yy -= 1
                draw_piece(p, x, yy, 1 if p < 0 else 0)
    for a in ACT:
        if a[5]:
            draw_piece(a[0], a[1] + ox, a[2] - cy + oy - int(a[4]), a[3])
    for o in FX:
        k = o[0]
        if k == 'p':
            px(o[1] + ox, o[2] - cy + oy)
        elif k == 'l':
            lineS(o[1] + ox, o[2] - cy + oy, o[3] + ox, o[4] - cy + oy)
        else:
            for yy in range(int(o[4])):
                for xx in range(int(o[3])):
                    px(o[1] + xx + ox, o[2] + yy - cy + oy)


def brackets(x, y):
    for dx in (0, 7):
        for dy in (0, 7):
            sx = 1 if dx == 0 else -1
            sy = 1 if dy == 0 else -1
            px(x + dx, y + dy)
            px(x + dx + sx, y + dy)
            px(x + dx, y + dy + sy)


def draw_ui(cy):
    # selected piece outline + legal move markers
    if sel >= 0:
        x = (sel & 7) * 8
        y = (sel >> 3) * 8 - cy
        lineS(x, y, x + 7, y)
        lineS(x, y + 7, x + 7, y + 7)
        lineS(x, y, x, y + 7)
        lineS(x + 7, y, x + 7, y + 7)
        for m in sel_moves:
            tx = (m[1] & 7) * 8
            ty = (m[1] >> 3) * 8 - cy
            if board[m[1]] or m[2] == 2:
                brackets(tx, ty)
            else:
                for i in range(2):
                    for j in range(2):
                        px(tx + 3 + i, ty + 3 + j)
    if (T // 8) % 3 != 0:
        brackets(cur_c * 8, cur_r * 8 - cy)


def draw_side():
    D.drawFilledRectangle(64, 0, 8, 40, 0)
    D.drawFilledRectangle(64, 0, 1, 40, 1)
    D.drawText(chr(97 + cur_c), 66, 0, 1)
    D.drawText(str(8 - cur_r), 66, 8, 1)
    if check_flag and (T // 6) & 1:
        D.drawText("!", 67, 16, 1)
    if mode == "think":
        D.drawText("|/-\\"[(T // 4) % 4], 66, 24, 1)
    else:
        D.drawText("W" if turn == 1 else "B", 66, 24, 1)
    D.drawText("EMH"[diff], 66, 32, 1)


def center(text, y):
    D.drawText(text, (72 - len(text) * 6) // 2, y, 1)


def menu_step():
    global diff, mode
    D.drawText("CHESS", 21, 0, 1)
    b = (T // 10) & 1
    draw_piece(2, 4, b, 0)
    draw_piece(-6, 60, 1 - b, 1)
    names = ("EASY", "MEDIUM", "HARD")
    for i in range(3):
        D.drawText(names[i], 24, 11 + i * 9, 1)
    D.drawText(">", 14 + ((T // 8) & 1), 11 + diff * 9, 1)
    if thumby.buttonU.justPressed():
        diff = (diff - 1) % 3
    if thumby.buttonD.justPressed():
        diff = (diff + 1) % 3
    if thumby.buttonA.justPressed():
        start_game()


def over_overlay():
    D.drawFilledRectangle(3, 6, 66, 28, 0)
    D.drawRectangle(3, 6, 66, 28, 1)
    center(res1, 9)
    center(res2, 18)
    center("PRESS A", 26)


def game_frame():
    global mode, cam
    if mode == "player":
        player_step()
        focus = cur_r * 8
    elif mode == "anim":
        anim_step()
        focus = int(ACT[0][2]) if ACT else cur_r * 8
    elif mode == "think":
        think_step()
        focus = 24
    else:
        if thumby.buttonA.justPressed():
            mode = "menu"
        focus = 24
    if mode == "menu":
        return
    tgt = min(24, max(0, focus + 4 - 20))
    cam += (tgt - cam) * 0.2
    cy = int(cam + 0.5)
    draw_scene(snap if (mode == "think" and think_gen is not None) else board, cy)
    if mode == "player":
        draw_ui(cy)
    draw_side()
    if mode == "over":
        over_overlay()


def main():
    global T
    while True:
        D.fill(0)
        T += 1
        if mode == "menu":
            menu_step()
        else:
            game_frame()
        D.update()


main()