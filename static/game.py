# game.py
from browser import document, html, timer, ajax, window
from random import random

canvas = document["gameCanvas"]
ctx = canvas.getContext("2d")
WIDTH, HEIGHT = 800, 400

# 圖片
bird_img = html.IMG(src="/static/images/bird.png")
pig_img = html.IMG(src="/static/images/pig.png")

# 遊戲狀態
SLING_X, SLING_Y = 120, 300
MAX_SHOTS = 10
shots_fired = 0
total_score = 0
current_shot_score = 0
mouse_down = False
mouse_pos = (SLING_X, SLING_Y)
projectile = None
sent = False

# ------------------------------------------
# 類別
# ------------------------------------------
class Pig:
    def __init__(self, x, y):
        self.x, self.y = x, y
        self.w, self.h = 40, 40
        self.alive = True

        # 房舍相對於小豬的相對位置
        self.house_blocks = [
            (0, 40, 120, 15),      # 地基
            (0, -10, 15, 50),      # 左牆
            (105, -10, 15, 50),    # 右牆
            (0, -25, 120, 15)      # 屋頂
        ]

    def draw(self):
        if self.alive:
            ctx.fillStyle = "saddlebrown"
            for rx, ry, rw, rh in self.house_blocks:
                ctx.fillRect(self.x + rx - 40, self.y + ry, rw, rh)

            ctx.drawImage(pig_img, self.x, self.y, self.w, self.h)

    def hit(self, px, py):
        return self.alive and self.x <= px <= self.x + self.w and self.y <= py <= self.y + self.h

    def relocate(self, other_pigs):
        MIN_DISTANCE = 120

        MIN_X = 450
        MAX_X = WIDTH - self.w - 120
        MIN_Y = 200
        MAX_Y = HEIGHT - self.h - 15

        while True:
            new_x = MIN_X + random() * (MAX_X - MIN_X)
            new_y = MIN_Y + random() * (MAX_Y - MIN_Y)

            too_close = False
            for p in other_pigs:
                if p is self or not p.alive:
                    continue
                if abs(new_x - p.x) < MIN_DISTANCE and abs(new_y - p.y) < MIN_DISTANCE:
                    too_close = True
                    break

            if not too_close:
                self.x = new_x
                self.y = new_y
                break


class Bird:
    def __init__(self, x, y, vx, vy):
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.w, self.h = 35, 35
        self.active = True

    def update(self):
        global current_shot_score, total_score
        if not self.active:
            return

        self.vy += 0.35
        self.x += self.vx
        self.y += self.vy

        if self.y > HEIGHT - self.h or self.x > WIDTH or self.x < 0:
            self.active = False

        for p in pigs:
            if p.hit(self.x + self.w / 2, self.y + self.h / 2):
                p.relocate(pigs)
                current_shot_score += 50
                total_score += 50
                document["score_display"].text = str(total_score)
                self.active = False
                break

    def draw(self):
        ctx.drawImage(bird_img, self.x, self.y, self.w, self.h)


# ------------------------------------------
# 遊戲控制
# ------------------------------------------
pigs = []

def init_level():
    global pigs
    pigs = []

    MIN_DISTANCE = 120
    positions = []

    MIN_X = 450
    MAX_X = WIDTH - 120
    MIN_Y = 200
    MAX_Y = HEIGHT - 40

    for _ in range(3):
        while True:
            x = MIN_X + random() * (MAX_X - MIN_X)
            y = MIN_Y + random() * (MAX_Y - MIN_Y)

            ok = True
            for px, py in positions:
                if abs(x - px) < MIN_DISTANCE and abs(y - py) < MIN_DISTANCE:
                    ok = False
                    break

            if ok:
                pigs.append(Pig(x, y))
                positions.append((x, y))
                break


def reset_sling_state():
    global shots_fired, current_shot_score, projectile, sent
    shots_fired = 0
    current_shot_score = 0
    projectile = None
    sent = False
    init_level()
    update_shots_remaining()


def start_new_game():
    global total_score
    total_score = 0
    document["score_display"].text = str(total_score)
    reset_sling_state()


def update_shots_remaining():
    document["shots_remaining"].text = str(MAX_SHOTS - shots_fired)


def get_mouse_pos(evt):
    return evt.x - canvas.offsetLeft, evt.y - canvas.offsetTop


def mousedown(evt):
    global mouse_down, mouse_pos
    if projectile is None and shots_fired < MAX_SHOTS:
        mouse_down = True
        mouse_pos = get_mouse_pos(evt)


def mousemove(evt):
    global mouse_pos
    if mouse_down:
        mouse_pos = get_mouse_pos(evt)


def mouseup(evt):
    global mouse_down, projectile, shots_fired, current_shot_score
    if mouse_down and projectile is None:
        current_shot_score = 0
        mouse_down = False
        end_pos = get_mouse_pos(evt)
        dx = SLING_X - end_pos[0]
        dy = SLING_Y - end_pos[1]
        projectile = Bird(SLING_X, SLING_Y, dx * 0.25, dy * 0.25)
        shots_fired += 1
        update_shots_remaining()


canvas.bind("mousedown", mousedown)
canvas.bind("mousemove", mousemove)
canvas.bind("mouseup", mouseup)


def draw_sling():
    ctx.strokeStyle = "black"
    ctx.lineWidth = 4
    if mouse_down:
        mx, my = mouse_pos
        ctx.beginPath()
        ctx.moveTo(SLING_X - 5, SLING_Y)
        ctx.lineTo(mx, my)
        ctx.stroke()
        ctx.beginPath()
        ctx.moveTo(SLING_X + 5, SLING_Y)
        ctx.lineTo(mx, my)
        ctx.stroke()
        ctx.drawImage(bird_img, mx - 17, my - 17, 35, 35)
    else:
        if projectile is None and shots_fired < MAX_SHOTS:
            ctx.drawImage(bird_img, SLING_X - 17, SLING_Y - 17, 35, 35)


def send_score():
    global sent, total_score
    if sent:
        return
    sent = True

    def on_complete(req):
        if req.status == 200:
            print("Score saved successfully.")
        else:
            print("Score submission failed.")

    req = ajax.ajax()
    req.bind('complete', on_complete)
    req.open("POST", "/submit_score", True)
    req.set_header("Content-Type", "application/json")
    req.send(window.JSON.stringify({"score": total_score}))


def loop():
    global projectile
    ctx.clearRect(0, 0, WIDTH, HEIGHT)

    for p in pigs:
        p.draw()

    game_over = shots_fired >= MAX_SHOTS

    if projectile:
        projectile.update()
        projectile.draw()

        if not projectile.active:
            projectile = None
            if game_over:
                send_score()
                timer.set_timeout(start_new_game, 2000)

    elif game_over:
        send_score()
        timer.set_timeout(start_new_game, 2000)

    draw_sling()


timer.set_interval(loop, 30)
start_new_game()
