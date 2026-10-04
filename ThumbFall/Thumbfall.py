# Pitfall-style jungle runner for Thumby (MicroPython)
# Controls: LEFT/RIGHT = run, A or UP = jump / let go of vine
# Goal: collect all 4 treasures before time runs out. 3 lives.
# Logs cost 100 points. Snakes and pits cost a life.

import thumby
import math
import random

# ---------- constants ----------
W = 72
GROUND = 30          # y of the walking surface (player's feet)
FLOOR = 39           # bottom of the pits / tunnel
PW = 3               # player width
PH = 8               # player height
GRAVITY = 0.35
JUMP = -2.9
SPEED = 1.0
FPS = 30
TIME_LIMIT = 120 * FPS   # 2 minutes

# Each screen: (hazard kind, has_treasure)
LEVELS = [
    ("none", 0),
    ("log", 0),
    ("pit", 1),
    ("log", 0),
    ("snake", 1),
    ("vine", 0),
    ("log", 1),
    ("pit", 0),
    ("vine", 1),
    ("log", 0),
    ("vine", 0),
    ("log", 1),
    ("log", 0),
    ("vine", 1),
    ("snake", 0),
]
TOTAL_TREASURE = sum(l[1] for l in LEVELS)

PIT = (28, 40)           # normal pit x range
VPIT = (20, 52)          # wide vine pit x range
ANCHOR_X = 36
ANCHOR_Y = 7
VINE_LEN = 20
VINE_AMP = 0.8

thumby.display.setFPS(FPS)


def beep(freq, ms):
    try:
        thumby.audio.play(freq, ms)
    except Exception:
        pass


# ---------- game state (globals) ----------
state = "title"
scr = 0
px = 2.0
py = float(GROUND)
vx = 0.0
vy = 0.0
on_ground = True
falling = False
grabbed = False
grab_cd = 0
hurt = 0
lives = 3
score = 0
timer = TIME_LIMIT
t = 0
got = [False] * len(LEVELS)
collected = 0
logs = []
tip_x = 36.0
tip_y = 27.0
prev_tip_x = 36.0
frame = 0


def new_game():
    global state, scr, px, py, vx, vy, on_ground, falling, grabbed, grab_cd
    global hurt, lives, score, timer, t, got, collected
    state = "play"
    scr = 0
    px = 2.0
    py = float(GROUND)
    vx = 0.0
    vy = 0.0
    on_ground = True
    falling = False
    grabbed = False
    grab_cd = 0
    hurt = 0
    lives = 3
    score = 100
    timer = TIME_LIMIT
    t = 0
    got = [False] * len(LEVELS)
    collected = 0
    setup_screen()


def setup_screen():
    global logs
    logs = []
    if LEVELS[scr][0] == "log":
        logs = [70.0, 34.0]


def pit_range():
    kind = LEVELS[scr][0]
    if kind == "pit":
        return PIT
    if kind == "vine":
        return VPIT
    return None


def solid(cx):
    r = pit_range()
    if r is None:
        return True
    return not (r[0] <= cx < r[1])


def overlap(ax, ay, aw, ah, bx, by, bw, bh):
    return ax < bx + bw and ax + aw > bx and ay < by + bh and ay + ah > by


def lose_life():
    global lives, state, px, py, vx, vy, on_ground, falling, grabbed, hurt
    lives -= 1
    beep(200, 300)
    if lives <= 0:
        state = "over"
        return
    px = 2.0
    py = float(GROUND)
    vx = 0.0
    vy = 0.0
    on_ground = True
    falling = False
    grabbed = False
    hurt = 45


# ---------- update ----------
def update():
    global px, py, vx, vy, on_ground, falling, grabbed, grab_cd, hurt
    global score, timer, t, scr, collected, state, tip_x, tip_y, prev_tip_x

    t += 1
    timer -= 1
    if timer <= 0:
        state = "over"
        return
    if hurt > 0:
        hurt -= 1
    if grab_cd > 0:
        grab_cd -= 1

    # vine position
    prev_tip_x = tip_x
    ang = VINE_AMP * math.sin(t * 0.07)
    tip_x = ANCHOR_X + VINE_LEN * math.sin(ang)
    tip_y = ANCHOR_Y + VINE_LEN * math.cos(ang)
    is_vine = LEVELS[scr][0] == "vine"

    dirn = 0
    if thumby.buttonR.pressed():
        dirn += 1
    if thumby.buttonL.pressed():
        dirn -= 1
    jump = thumby.buttonA.justPressed() or thumby.buttonU.justPressed()

    if grabbed:
        px = tip_x - 1
        py = tip_y - 1 + PH
        if jump:
            grabbed = False
            grab_cd = 15
            vx = (tip_x - prev_tip_x) * 1.1
            vy = -2.0
            on_ground = False
            beep(600, 60)
    else:
        if not falling:
            if on_ground:
                vx = dirn * SPEED
                if jump:
                    vy = JUMP
                    on_ground = False
                    beep(500, 60)
            elif dirn:
                vx = dirn * SPEED

        if not on_ground:
            vy += GRAVITY
        old_py = py
        py += vy
        if not falling:
            px += vx

        cx = int(px + 1)
        if not falling and not on_ground and vy >= 0:
            if solid(cx) and py >= GROUND and old_py <= GROUND + 0.5:
                py = float(GROUND)
                vy = 0.0
                on_ground = True
        if on_ground and not solid(cx):
            on_ground = False
            vy = 0.0

        if (not on_ground and not falling and py > GROUND + 3 and vy >= 0):
            falling = True
            vx = 0.0

        # grab the vine
        if (is_vine and not on_ground and not falling and grab_cd == 0):
            hx = px + 1
            hy = py - PH + 1
            dx = hx - tip_x
            dy = hy - tip_y
            if dx * dx + dy * dy < 20:
                grabbed = True
                vy = 0.0
                beep(800, 40)

        if py >= FLOOR:
            lose_life()
            return

        # screen transitions
        if not falling:
            if px > W - PW:
                if scr < len(LEVELS) - 1:
                    scr += 1
                    px = 0.0
                    setup_screen()
                else:
                    px = float(W - PW)
            elif px < 0:
                if scr > 0:
                    scr -= 1
                    px = float(W - PW)
                    setup_screen()
                else:
                    px = 0.0

    # hazards
    kind = LEVELS[scr][0]
    top = py - PH
    if kind == "log":
        for i in range(len(logs)):
            logs[i] -= 0.8
            if logs[i] < -6:
                logs[i] = 74.0
            if hurt == 0 and overlap(px, top, PW, PH, logs[i], 26, 6, 4):
                score = max(0, score - 100)
                hurt = 45
                beep(250, 120)
    elif kind == "snake":
        if hurt == 0 and overlap(px, top, PW, PH, 36, 26, 6, 4):
            lose_life()
            return

    # treasure
    if LEVELS[scr][1] and not got[scr]:
        if overlap(px, top, PW, PH, 60, 25, 4, 5):
            got[scr] = True
            collected += 1
            score += 1000
            beep(1000, 150)
            if collected >= TOTAL_TREASURE:
                state = "win"


# ---------- drawing ----------
def draw_player():
    if hurt > 0 and (t // 3) % 2 == 0:
        return
    d = thumby.display
    x = int(px)
    top = int(py) - PH
    d.drawFilledRectangle(x, top, 3, 2, 1)           # head
    d.drawLine(x + 1, top + 2, x + 1, top + 5, 1)    # body
    if grabbed:
        d.setPixel(x, top - 1, 1)
        d.setPixel(x + 2, top - 1, 1)
        d.drawLine(x, top + 6, x, top + 7, 1)
        d.drawLine(x + 2, top + 6, x + 2, top + 7, 1)
        return
    d.setPixel(x, top + 3, 1)                        # arms
    d.setPixel(x + 2, top + 3, 1)
    if on_ground and vx != 0 and (t // 4) % 2 == 0:
        d.drawLine(x, top + 6, x, top + 7, 1)
        d.drawLine(x + 2, top + 6, x + 2, top + 7, 1)
    elif not on_ground:
        d.drawLine(x, top + 6, x - 1, top + 7, 1)
        d.drawLine(x + 2, top + 6, x + 3, top + 7, 1)
    else:
        d.drawLine(x + 1, top + 6, x + 1, top + 7, 1)


def draw_scene():
    d = thumby.display
    kind = LEVELS[scr][0]

    # HUD
    d.drawText(str(score), 0, 0, 1)
    secs = timer // FPS
    d.drawText("%d:%02d" % (secs // 60, secs % 60), 28, 0, 1)
    for i in range(lives):
        d.drawFilledRectangle(69 - i * 4, 1, 3, 5, 1)

    # canopy
    for x in range(W):
        if (x + scr) % 3 != 0:
            d.setPixel(x, 8, 1)
        if (x + scr) % 2 == 0:
            d.setPixel(x, 9, 1)
        if (x * 7 + scr * 5) % 5 == 0:
            d.setPixel(x, 10, 1)

    # tree trunks (fixed per screen)
    for k in range(3):
        tx = (scr * 17 + k * 23 + 5) % 68
        if kind == "vine" and abs(tx - ANCHOR_X) < 4:
            continue
        d.drawLine(tx, 11, tx, GROUND - 1, 1)

    # ground
    r = pit_range()
    if r is None:
        d.drawFilledRectangle(0, GROUND, W, 2, 1)
    else:
        d.drawFilledRectangle(0, GROUND, r[0], 2, 1)
        d.drawFilledRectangle(r[1], GROUND, W - r[1], 2, 1)
        d.drawLine(r[0], GROUND, r[0], FLOOR, 1)
        d.drawLine(r[1] - 1, GROUND, r[1] - 1, FLOOR, 1)
    d.drawLine(0, FLOOR, W, FLOOR, 1)
    # tunnel texture
    for x in range(0, W, 4):
        if r is None or not (r[0] <= x < r[1]):
            d.setPixel(x, 34, 1)

    # vine
    if kind == "vine":
        d.drawLine(ANCHOR_X, ANCHOR_Y, int(tip_x), int(tip_y), 1)

    # hazards
    if kind == "log":
        for lx in logs:
            d.drawFilledRectangle(int(lx), 26, 6, 4, 1)
            d.setPixel(int(lx) + 2, 27, 0)
            d.setPixel(int(lx) + 3, 28, 0)
    elif kind == "snake":
        sx = 36
        d.drawFilledRectangle(sx, 28, 6, 2, 1)
        d.drawFilledRectangle(sx + 4, 26, 2, 3, 1)
        d.setPixel(sx + 5, 26, 0)

    # treasure
    if LEVELS[scr][1] and not got[scr]:
        d.drawFilledRectangle(60, 26, 4, 4, 1)
        d.setPixel(61, 25, 1)
        d.setPixel(62, 25, 1)
        d.setPixel(61, 27, 0)

    draw_player()


def draw_center(text, y):
    x = (W - len(text) * 6) // 2
    thumby.display.drawText(text, max(0, x), y, 1)


# ---------- main loop ----------
while True:
    thumby.display.fill(0)

    if state == "title":
        draw_center("THUMBFALL", 6)
        draw_center("JUNGLE RUN", 15)
        draw_center("A: START", 28)
        if thumby.buttonA.justPressed():
            new_game()

    elif state == "play":
        update()
        if state == "play":
            draw_scene()
        else:
            continue

    elif state == "over":
        draw_center("GAME OVER", 6)
        draw_center("SCORE", 16)
        draw_center(str(score), 24)
        draw_center("A: RETRY", 32)
        if thumby.buttonA.justPressed():
            new_game()

    elif state == "win":
        draw_center("YOU WIN!", 6)
        draw_center("SCORE", 16)
        draw_center(str(score + (timer // FPS) * 10), 24)
        draw_center("A: AGAIN", 32)
        if thumby.buttonA.justPressed():
            new_game()

    thumby.display.update()
