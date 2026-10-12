# -*- coding: utf-8 -*-
"""4컷 만화 렌더러 (2026-10-08 신설).

왜 만들었나
  텍스트 전용 글은 피드에서 다른 썰 계정과 구분이 안 된다. 일관된 그림체는
  "아 이 계정" 하고 알아보게 만드는 유일한 자산이고, 그게 팔로우 이유가 된다.
  545만 조회에 팔로워 277명인 상태에서 필요한 건 도달이 아니라 그 구분이다.

왜 AI 이미지 생성이 아닌가
  1) 네 컷에서 같은 얼굴이 유지되지 않는다.
  2) 한글 말풍선 글자가 깨진다.
  캐릭터를 도형으로 그리고 대사는 폰트로 찍으면 둘 다 해결된다. 비용도 0이다.

캐릭터 비율은 profile_ssuldaeri.png 를 픽셀 단위로 측정해 맞췄다.
  헤어라인 -0.55s / 눈썹 -0.46s / 눈 -0.11s(간격 ±0.45s) / 입 +0.52s / 턱 +1.0s
"""
import os
from PIL import Image, ImageDraw, ImageFont

# 맥과 리눅스 양쪽에서 도는 한글 폰트 탐색 (make_card.py와 같은 방식)
FONT_CANDIDATES = [
    os.environ.get("FONT_PATH", ""),
    "/System/Library/Fonts/Supplemental/AppleSDGothicNeo.ttc",
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    "/Library/Fonts/AppleGothic.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Black.ttc",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
]
_BOLD_FIRST = [
    os.environ.get("FONT_PATH_BOLD", ""),
    "/System/Library/Fonts/Supplemental/AppleSDGothicNeo.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Black.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
]

def f(size, bold=False):
    """한글이 나오는 폰트를 찾을 때까지 후보를 훑는다. ttc 인덱스도 순차 시도."""
    for path in (_BOLD_FIRST + FONT_CANDIDATES) if bold else FONT_CANDIDATES:
        if not path or not os.path.exists(path):
            continue
        for idx in (2, 0):
            try:
                ft = ImageFont.truetype(path, size, index=idx)
                ft.getbbox("썰")
                return ft
            except Exception:
                continue
    return ImageFont.load_default()


YELLOW = (255, 224, 74)
HAIR   = (20, 20, 22)
SKIN   = (255, 232, 214)
MOUTH  = (150, 60, 55)
JACKET = (38, 50, 84)
SHIRT  = (252, 247, 238)
TIE    = (230, 70, 60)
INKC   = (20, 20, 22)

CAST = {
    "me":   dict(hair=HAIR,           jacket=JACKET,         tie=TIE,          glasses=False),
    "boss": dict(hair=(108, 110, 118), jacket=(118, 122, 132), tie=(64, 68, 82), glasses=True),
}

def draw_character(img, cx, cy, s, who="me", expr="normal", pose="none", fx=None, flip=False):
    c = CAST[who]
    lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    lw = max(3, int(s * 0.07))

    # ── 몸통 (pose에 따라 어깨 폭/높이가 바뀐다) ──
    bw, bh = s * 2.3, s * 1.5
    by = cy + s * 1.06
    if pose == "slump":                 # 어깨 처짐: 좁고 아래로
        bw, by = s * 2.0, cy + s * 1.20
    d.rounded_rectangle([cx - bw/2, by, cx + bw/2, by + bh], radius=s*0.40,
                        fill=c["jacket"], outline=INKC, width=lw)
    d.polygon([(cx - s*0.44, by - s*0.03), (cx, by + s*0.74), (cx + s*0.44, by - s*0.03)],
              fill=SHIRT, outline=INKC)
    d.polygon([(cx, by + s*0.24), (cx - s*0.15, by + s*0.48), (cx, by + s*1.04),
               (cx + s*0.15, by + s*0.48)], fill=c["tie"], outline=INKC)

    # ── 얼굴 ──
    d.ellipse([cx - s, cy - s, cx + s, cy + s], fill=SKIN, outline=INKC, width=lw)

    # ── 머리카락 (바가지. 평평한 아랫변 = 헤어라인 -0.55s) ──
    d.pieslice([cx - s*1.09, cy - s*1.47, cx + s*1.09, cy + s*0.37],
               180, 360, fill=c["hair"], outline=INKC, width=lw)

    ex, ey = s*0.45, cy - s*0.11
    er = s*0.105

    # ── 눈썹 (-0.46s) ──
    byy = cy - s*0.46
    for sg in (-1, 1):
        x0, x1 = cx + sg*ex - s*0.22, cx + sg*ex + s*0.22
        if expr in ("angry", "smug"):
            p = [(x0, byy - sg*s*0.09), (x1, byy + sg*s*0.09)]
        elif expr in ("sad", "flat"):
            p = [(x0, byy + sg*s*0.09), (x1, byy - sg*s*0.09)]
        elif expr == "shock":
            p = [(x0, byy - s*0.10), (x1, byy - s*0.10)]
        else:
            p = [(x0, byy - sg*s*0.06), (x1, byy + sg*s*0.06)]
        d.line(p, fill=INKC, width=int(lw*1.25))

    # ── 눈 ──
    if expr == "flat":
        for sg in (-1, 1):
            d.line([(cx + sg*ex - er, ey), (cx + sg*ex + er, ey)], fill=INKC, width=int(lw*1.3))
    else:
        r = er * (1.5 if expr == "shock" else 1.0)
        for sg in (-1, 1):
            d.ellipse([cx + sg*ex - r, ey - r*1.3, cx + sg*ex + r, ey + r*1.3], fill=INKC)

    # ── 안경 (팀장 구분용) ──
    if c["glasses"]:
        gr = s*0.27
        for sg in (-1, 1):
            d.ellipse([cx + sg*ex - gr, ey - gr, cx + sg*ex + gr, ey + gr],
                      outline=INKC, width=int(lw*0.9))
        d.line([(cx - ex + gr, ey), (cx + ex - gr, ey)], fill=INKC, width=int(lw*0.9))

    # ── 입 (+0.52s) ──
    my = cy + s*0.52
    if expr == "shock":
        d.ellipse([cx - s*0.16, my - s*0.17, cx + s*0.16, my + s*0.23], fill=MOUTH, outline=INKC, width=lw)
    elif expr == "angry":
        d.arc([cx - s*0.26, my - s*0.02, cx + s*0.26, my + s*0.3], 200, 340, fill=INKC, width=int(lw*1.3))
    elif expr == "sad":
        d.arc([cx - s*0.24, my - s*0.04, cx + s*0.24, my + s*0.34], 200, 340, fill=INKC, width=int(lw*1.2))
    elif expr == "flat":
        d.line([(cx - s*0.19, my), (cx + s*0.19, my)], fill=INKC, width=int(lw*1.3))
    elif expr == "smug":
        d.arc([cx - s*0.26, my - s*0.24, cx + s*0.26, my + s*0.16], 20, 160, fill=INKC, width=int(lw*1.3))
    else:
        d.ellipse([cx - s*0.15, my - s*0.09, cx + s*0.15, my + s*0.15], fill=MOUTH, outline=INKC, width=lw)

    # ── 팔 (포즈) ──
    aw = s * 0.32
    sh_y = by + s * 0.46                       # 어깨 높이
    if pose == "crossed":                      # 팔짱: 두 팔이 가슴 앞에서 엇갈린다
        for sg in (-1, 1):
            x0, y0 = cx + sg*s*0.98, sh_y + s*0.02
            x1, y1 = cx - sg*s*0.30, sh_y + s*0.40
            d.line([(x0, y0), (x1, y1)], fill=INKC, width=int(aw + lw*2))
            d.line([(x0, y0), (x1, y1)], fill=c["jacket"], width=int(aw))
        for sg in (-1, 1):                     # 손은 반대쪽 팔 위에
            hx, hy = cx - sg*s*0.34, sh_y + s*0.40
            d.ellipse([hx - aw*0.56, hy - aw*0.56, hx + aw*0.56, hy + aw*0.56],
                      fill=SKIN, outline=INKC, width=lw)
    elif pose == "raised":                     # 손들기: 얼굴 바깥으로 뺀다
        hx, hy = cx + s*1.48, cy - s*0.42
        d.line([(cx + s*0.96, sh_y), (hx, hy)], fill=INKC, width=int(aw + lw*2))
        d.line([(cx + s*0.96, sh_y), (hx, hy)], fill=c["jacket"], width=int(aw))
        d.ellipse([hx - aw*0.70, hy - aw*0.70, hx + aw*0.70, hy + aw*0.70],
                  fill=SKIN, outline=INKC, width=lw)
    elif pose == "point":                      # 손가락질: 옆으로 쭉
        hx, hy = cx + s*1.62, cy + s*0.60
        d.line([(cx + s*0.94, sh_y), (hx, hy)], fill=INKC, width=int(aw + lw*2))
        d.line([(cx + s*0.94, sh_y), (hx, hy)], fill=c["jacket"], width=int(aw))
        d.ellipse([hx - aw*0.62, hy - aw*0.62, hx + aw*0.62, hy + aw*0.62],
                  fill=SKIN, outline=INKC, width=lw)
        d.line([(hx + aw*0.2, hy), (hx + aw*1.1, hy)], fill=INKC, width=int(lw*1.6))

    # ── 감정 효과 ──
    if fx == "sweat":                   # 땀방울
        sx_, sy_ = cx + s*0.86, cy - s*0.52
        d.ellipse([sx_ - s*0.14, sy_, sx_ + s*0.14, sy_ + s*0.34],
                  fill=(150, 212, 240), outline=INKC, width=int(lw*0.8))
        d.polygon([(sx_ - s*0.09, sy_ + s*0.06), (sx_ + s*0.09, sy_ + s*0.06),
                   (sx_, sy_ - s*0.16)], fill=(150, 212, 240), outline=INKC)
    elif fx == "anger":                 # 분노 혈관
        ax, ay = cx - s*0.78, cy - s*0.80
        r = s*0.20
        for a in (0, 1):
            d.line([(ax - r + a*r, ay - r), (ax + a*r, ay + r)], fill=(220, 50, 50), width=int(lw*1.1))
            d.line([(ax - r, ay - r + a*r), (ax + r, ay + a*r)], fill=(220, 50, 50), width=int(lw*1.1))
    elif fx == "shock":                 # 충격 집중선
        import math
        for a in range(0, 360, 30):
            rad = math.radians(a)
            x0 = cx + math.cos(rad) * s*1.16
            y0 = cy + math.sin(rad) * s*1.16
            x1 = cx + math.cos(rad) * s*1.44
            y1 = cy + math.sin(rad) * s*1.44
            d.line([(x0, y0), (x1, y1)], fill=INKC, width=int(lw*0.9))
    elif fx == "dots":                  # 말잇못
        for k in range(3):
            dx = cx + s*0.30 + k*s*0.26
            d.ellipse([dx - s*0.07, cy - s*1.28, dx + s*0.07, cy - s*1.14], fill=INKC)

    if flip:
        lay = lay.transpose(Image.FLIP_LEFT_RIGHT)
    img.alpha_composite(lay)


WALL, WALL2   = (255, 226, 92), (255, 240, 170)
FLOOR, FLOOR2 = (226, 192, 70), (230, 210, 132)
FURN, FURN_L  = (58, 72, 110), (112, 126, 160)
GLASS, WHITE  = (176, 214, 232), (252, 247, 238)
INK = (20, 20, 22)

def _blinds(d, x0, y0, x1, y1, lw=3):
    d.rectangle([x0, y0, x1, y1], fill=GLASS, outline=INK, width=lw)
    step = max(8, (y1 - y0) // 6)
    yy = y0 + step
    while yy < y1 - 2:
        d.line([(x0, yy), (x1, yy)], fill=(138, 178, 200), width=2)
        yy += step

def draw_scene(img, kind="plain", light=False, hz_ratio=0.86):
    """hz_ratio: 벽/바닥 경계 위치. 기본 0.86이면 인물 어깨 아래로 지나간다."""
    W, H = img.size
    d = ImageDraw.Draw(img)
    wall  = WALL2 if light else WALL
    floor = FLOOR2 if light else FLOOR
    lw, hz = 3, int(H * hz_ratio)
    band = int(H * 0.30)          # 소품을 둘 벽 상단 띠 (머리 위)

    d.rectangle([0, 0, W, H], fill=wall)
    if kind == "plain":
        return
    d.rectangle([0, hz, W, H], fill=floor)
    d.line([(0, hz), (W, hz)], fill=INK, width=lw)

    if kind == "meeting":          # 회의실: 블라인드 + 앞쪽 테이블
        _blinds(d, int(W*0.06), int(H*0.30), int(W*0.40), band + int(H*0.22), lw)
        ty = int(H * 0.88)
        d.rectangle([-20, ty, W+20, H+20], fill=FURN, outline=INK, width=lw)
        d.rectangle([-20, ty, W+20, ty + int(H*0.035)], fill=FURN_L)

    elif kind == "office":         # 사무실: 오른쪽 파티션 + 책상
        d.rectangle([int(W*0.70), int(H*0.26), W+20, hz], fill=FURN_L, outline=INK, width=lw)
        dy = int(H * 0.89)
        d.rectangle([-20, dy, W+20, H+20], fill=FURN, outline=INK, width=lw)

    elif kind == "pantry":         # 탕비실: 상부장 + 조리대
        d.rectangle([int(W*0.06), int(H*0.26), int(W*0.44), band + int(H*0.14)],
                    fill=FURN_L, outline=INK, width=lw)
        cy_ = int(H * 0.87)
        d.rectangle([-20, cy_, W+20, H+20], fill=FURN, outline=INK, width=lw)
        d.rectangle([-20, cy_, W+20, cy_ + int(H*0.03)], fill=WHITE)

    elif kind == "home":           # 집: 창문 + 소파 등받이
        d.rectangle([int(W*0.62), int(H*0.26), int(W*0.92), band + int(H*0.16)],
                    fill=GLASS, outline=INK, width=lw)
        d.line([(int(W*0.77), int(H*0.26)), (int(W*0.77), band + int(H*0.16))], fill=INK, width=lw)
        sy = int(H * 0.86)
        d.rounded_rectangle([-30, sy, W+30, H+40], 22, fill=FURN_L, outline=INK, width=lw)

    elif kind == "hall":           # 복도: 문 두 개 (머리 양옆으로)
        for fx in (0.03, 0.70):
            d.rectangle([int(W*fx), int(H*0.24), int(W*(fx+0.27)), hz],
                        fill=FURN_L, outline=INK, width=lw)
            d.ellipse([int(W*(fx+0.225)), int(H*0.56), int(W*(fx+0.25)), int(H*0.59)], fill=INK)



BG     = (250, 249, 247)
PANEL  = (255, 226, 92)      # 컷 배경 (프로필 노랑 계열)
PANEL2 = (255, 240, 170)     # 밝은 변형
INK    = (24, 24, 28)
MUTED  = (120, 120, 128)
CORAL  = (255, 90, 95)
W, M, GAP = 1080, 48, 18


def wrap(d, t, font, mw):
    out, line = [], ""
    for w_ in t.split(" "):
        s = (line + " " + w_).strip()
        if d.textlength(s, font=font) <= mw: line = s; continue
        if line: out.append(line)
        if d.textlength(w_, font=font) <= mw: line = w_
        else:
            c = ""
            for ch in w_:
                if d.textlength(c+ch, font=font) <= mw: c += ch
                else: out.append(c); c = ch
            line = c
    if line: out.append(line)
    return out

def bubble(d, x, y, text, font, maxw, tail_x, tail_dir=1, fill=SHIRT):
    """말풍선. (x,y)=좌상단, tail_dir=1이면 꼬리가 아래로."""
    lines = wrap(d, text, font, maxw)
    lh = font.size + 12
    tw = max(d.textlength(l, font=font) for l in lines)
    pw, ph = tw + 44, len(lines)*lh + 30
    d.rounded_rectangle([x, y, x+pw, y+ph], radius=22, fill=fill, outline=INKC, width=4)
    ty = y + 15
    for l in lines:
        d.text((x + pw/2, ty), l, font=font, fill=INK, anchor="ma"); ty += lh
    # 꼬리
    tx = min(max(tail_x, x+30), x+pw-30)
    if tail_dir > 0:
        d.polygon([(tx-16, y+ph-3), (tx+16, y+ph-3), (tx-4, y+ph+26)], fill=fill, outline=INKC)
        d.line([(tx-15, y+ph-2), (tx+15, y+ph-2)], fill=fill, width=5)
    return ph

def render(hook, cuts, handle="@ssuldaeri", out="toon.png"):
    probe = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    fh, fnar, fdlg = f(40, True), f(24), f(30, True)
    pw = (W - 2*M - GAP) // 2
    ph = 430

    hl = wrap(probe, hook, fh, W - 2*M)[:2]
    head = 128 + len(hl)*54 + 20
    H = head + 2*ph + GAP + 92

    img = Image.new("RGBA", (W, H), BG + (255,))
    d = ImageDraw.Draw(img)

    tag, ft = "주워들은 썰", f(25, True)
    tw = d.textlength(tag, font=ft)
    d.rounded_rectangle([M, 48, M+tw+38, 96], 24, fill=CORAL)
    d.text((M+19, 72), tag, font=ft, fill=(255,255,255), anchor="lm")
    y = 128
    for l in hl: d.text((M, y), l, font=fh, fill=INK); y += 54

    for i, c in enumerate(cuts):
        px = M + (i % 2)*(pw + GAP)
        py = head + (i // 2)*(ph + GAP)
        cut = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
        draw_scene(cut, c.get("scene", "plain"), light=(i % 2 == 1))
        cd = ImageDraw.Draw(cut)

        # 캐릭터: 1명이면 가운데, 2명이면 좌/우
        who = c["chars"]
        s = 60
        base_y = ph - 132
        if len(who) == 1:
            spots = [(pw//2, base_y)]
        else:
            spots = [(int(pw*0.27), base_y), (int(pw*0.73), base_y)]
        for spec, (sx, sy) in zip(who, spots):
            w_, e = spec[0], spec[1]
            po = spec[2] if len(spec) > 2 else "none"
            fxx = spec[3] if len(spec) > 3 else None
            draw_character(cut, sx, sy, s, w_, e, pose=po, fx=fxx)

        # 말풍선
        if c.get("line"):
            spk = c.get("speaker", 0)
            tailx = spots[spk][0]
            bw_max = pw - 120
            lines = wrap(cd, c["line"], fdlg, bw_max)
            twid = max(cd.textlength(l, font=fdlg) for l in lines)
            bx = min(max(tailx - (twid+44)/2, 24), pw - twid - 68)
            bubble(cd, bx, 86, c["line"], fdlg, bw_max, tailx)

        # 지문 (상단 띠)
        if c.get("narration"):
            nl = wrap(cd, c["narration"], fnar, pw - 52 - 58)
            bh = len(nl)*32 + 20
            cd.rectangle([0, 0, pw, bh], fill=(255, 255, 255, 235))
            cd.line([(0, bh), (pw, bh)], fill=INKC, width=3)
            ny = 10
            for l in nl:
                cd.text((26, ny), l, font=fnar, fill=(60, 60, 66)); ny += 32

        cd.rounded_rectangle([1, 1, pw-2, ph-2], 20, outline=INKC, width=4)
        mask = Image.new("L", (pw, ph), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, pw-1, ph-1], 20, fill=255)
        img.paste(cut, (px, py), mask)

        d.ellipse([px+pw-56, py+16, px+pw-16, py+56], fill=CORAL, outline=INKC, width=3)
        d.text((px+pw-36, py+36), str(i+1), font=f(22, True), fill=(255,255,255), anchor="mm")

    fy = head + 2*ph + GAP + 30
    d.text((M, fy), handle, font=f(25, True), fill=INK)
    d.text((W-M, fy+3), "전해 들은 얘기와 제보를 각색함 · 제보는 DM", font=f(21), fill=MUTED, anchor="ra")
    img.convert("RGB").save(out, "PNG", optimize=True)
    return out, (W, H)


# ─────────────────────────────────────────────────────────────
# 발행 파이프라인 진입점
# ─────────────────────────────────────────────────────────────
def render_toon(thread: dict, out_path: str) -> bool:
    """뱅크 항목의 panels로 4컷을 그린다. 실패하면 False를 돌려주고
    호출한 쪽은 그냥 텍스트로 발행하면 된다. 만화 때문에 발행이 멈추면 안 된다."""
    panels = thread.get("panels")
    if not panels or len(panels) != 4:
        return False
    try:
        cuts = []
        for p in panels:
            cuts.append({
                "scene": p.get("scene", "plain"),
                "narration": p.get("narration", ""),
                "line": p.get("line", ""),
                "speaker": int(p.get("speaker", 0)),
                "chars": [tuple(c) for c in p.get("chars", [["me", "normal"]])],
            })
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        render(thread["hook"], cuts, out=out_path)
        return os.path.exists(out_path)
    except Exception as e:
        print(f"[toon] 렌더 실패(텍스트로 계속 진행): {e}")
        return False
