"""
카드 이미지 생성 v2 (Pillow, 무료/외부 API 불필요).
- 브랜드 컬러 그라데이션 카드 + 그림자 + 원형 VS 배지 + 워터마크
- Instagram 캐러셀용 서사 텍스트 슬라이드 카드 생성 기능 포함
"""
import os
from PIL import Image, ImageDraw, ImageFont, ImageFilter

FONT_CANDIDATES = [
    os.environ.get("FONT_PATH", ""),
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/System/Library/Fonts/Supplemental/AppleSDGothicNeo.ttc",
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    "/Library/Fonts/AppleGothic.ttf",
    "/System/Library/Fonts/AppleGothic.ttf",
]

# 브랜드 컬러 (프로필 마스코트와 통일감)
CORAL_TOP = (255, 138, 120)
CORAL_BOT = (255, 90, 95)
BLUE_TOP = (90, 120, 255)
BLUE_BOT = (48, 60, 220)
BG_COLOR = (250, 249, 247)
TEXT_DARK = (30, 30, 35)
MUTED = (140, 140, 140)


def load_font(size: int, bold=True) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if path and os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def vertical_gradient(size, top_color, bottom_color):
    w, h = size
    base = Image.new("RGB", (1, h), color=0)
    for y in range(h):
        t = y / max(h - 1, 1)
        r = int(top_color[0] + (bottom_color[0] - top_color[0]) * t)
        g = int(top_color[1] + (bottom_color[1] - top_color[1]) * t)
        b = int(top_color[2] + (bottom_color[2] - top_color[2]) * t)
        base.putpixel((0, y), (r, g, b))
    return base.resize((w, h))


def rounded_mask(size, radius):
    mask = Image.new("L", size, 0)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle([(0, 0), (size[0] - 1, size[1] - 1)], radius=radius, fill=255)
    return mask


def paste_shadow(base, box, radius, blur=18, offset=(0, 10), alpha=70):
    x0, y0 = box[0]
    x1, y1 = box[1]
    w, h = x1 - x0, y1 - y0
    shadow_layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    shadow_shape = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(shadow_shape)
    d.rounded_rectangle([(0, 0), (w - 1, h - 1)], radius=radius, fill=(0, 0, 0, alpha))
    shadow_layer.paste(shadow_shape, (x0 + offset[0], y0 + offset[1]))
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(blur))
    base.alpha_composite(shadow_layer)


def draw_gradient_card(base, box, radius, top_color, bottom_color):
    x0, y0 = box[0]
    x1, y1 = box[1]
    w, h = x1 - x0, y1 - y0
    grad = vertical_gradient((w, h), top_color, bottom_color).convert("RGBA")
    mask = rounded_mask((w, h), radius)
    card = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    card.paste(grad, (0, 0), mask)
    base.alpha_composite(card, (x0, y0))


def fit_font(draw, text, max_w, start_size, min_size=32, bold_path=None):
    """텍스트가 max_w를 넘지 않는 선에서 최대한 큰 폰트 크기를 찾는다."""
    size = start_size
    while size > min_size:
        font = load_font(size)
        bb = draw.textbbox((0, 0), text, font=font)
        if (bb[2] - bb[0]) <= max_w:
            return font
        size -= 4
    return load_font(min_size)


def wrap_text(draw, text, font, max_w):
    """공백 기준으로 단어 단위 줄바꿈 (자동 안전장치용)."""
    words = text.split(" ")
    lines = []
    current = ""
    for w in words:
        trial = (current + " " + w).strip()
        bb = draw.textbbox((0, 0), trial, font=font)
        if bb[2] - bb[0] <= max_w or not current:
            current = trial
        else:
            lines.append(current)
            current = w
    if current:
        lines.append(current)
    return lines


def split_and_wrap(draw, text, font, max_w):
    """명시적 \n이 있으면 그 지점을 우선 줄바꿈 기준으로 쓰고,
    그래도 폭을 넘는 줄만 추가로 단어 단위 자동 줄바꿈한다."""
    result = []
    for manual_line in text.split("\n"):
        result.extend(wrap_text(draw, manual_line, font, max_w))
    return result


def fit_wrapped_sub(draw, text, max_w, start_size=36, min_size=22, max_lines=3):
    """줄바꿈 후 max_lines를 넘지 않는 선에서 최대한 큰 폰트를 찾는다."""
    size = start_size
    while size > min_size:
        font = load_font(size)
        lines = split_and_wrap(draw, text, font, max_w)
        if len(lines) <= max_lines:
            return font, lines
        size -= 2
    font = load_font(min_size)
    return font, split_and_wrap(draw, text, font, max_w)


def centered_multiline(draw, box, main, sub_lines, main_font, sub_font, main_color, sub_color,
                        block_gap=28, line_gap=10):
    cx = (box[0][0] + box[1][0]) / 2
    cy = (box[0][1] + box[1][1]) / 2

    mb = draw.textbbox((0, 0), main, font=main_font)
    mw, mh = mb[2] - mb[0], mb[3] - mb[1]

    line_metrics = []
    for line in sub_lines:
        lb = draw.textbbox((0, 0), line, font=sub_font)
        line_metrics.append((lb[2] - lb[0], lb[3] - lb[1], lb[1]))
    sub_total_h = sum(h for _, h, _ in line_metrics) + line_gap * max(len(line_metrics) - 1, 0)

    total_h = mh + block_gap + sub_total_h
    top = cy - total_h / 2

    draw.text((cx - mw / 2, top - mb[1]), main, font=main_font, fill=main_color)

    y = top + mh + block_gap
    for line, (lw, lh, ltop) in zip(sub_lines, line_metrics):
        draw.text((cx - lw / 2, y - ltop), line, font=sub_font, fill=sub_color)
        y += lh + line_gap


def make_vs_card(option_a: str, option_a_sub: str, option_b: str, option_b_sub: str, out_path: str,
                  handle: str = "@pick1_daily"):
    W, H = 1080, 1080
    img = Image.new("RGBA", (W, H), BG_COLOR + (255,))
    draw = ImageDraw.Draw(img)

    brand_font = load_font(38)
    vs_font = load_font(46)
    watermark_font = load_font(26)

    # 상단 브랜드 라벨
    brand_text = "오늘의 밸런스게임"
    bb = draw.textbbox((0, 0), brand_text, font=brand_font)
    bw = bb[2] - bb[0]
    draw.text(((W - bw) / 2, 84), brand_text, font=brand_font, fill=(70, 70, 75))
    draw.line([(W / 2 - 40, 140), (W / 2 + 40, 140)], fill=(220, 120, 110), width=4)

    pad = 64
    gap = 28
    box_w = (W - pad * 2 - gap) // 2
    box_top = 210
    box_h = 620
    radius = 36

    box_a = [(pad, box_top), (pad + box_w, box_top + box_h)]
    box_b = [(pad + box_w + gap, box_top), (W - pad, box_top + box_h)]

    # 그림자
    paste_shadow(img, box_a, radius)
    paste_shadow(img, box_b, radius)

    # 그라데이션 카드
    draw_gradient_card(img, box_a, radius, CORAL_TOP, CORAL_BOT)
    draw_gradient_card(img, box_b, radius, BLUE_TOP, BLUE_BOT)

    draw = ImageDraw.Draw(img)
    text_max_w = box_w - 56  # 카드 안쪽 여백 확보
    font_a = fit_font(draw, option_a, text_max_w, start_size=84, min_size=40)
    font_b = fit_font(draw, option_b, text_max_w, start_size=84, min_size=40)
    main_font_size = min(font_a.size, font_b.size)
    main_font = load_font(main_font_size)

    quoted_a = f"“{option_a_sub}”"
    quoted_b = f"“{option_b_sub}”"

    sub_font_a, lines_a = fit_wrapped_sub(draw, quoted_a, text_max_w, start_size=36, min_size=22, max_lines=3)
    sub_font_b, lines_b = fit_wrapped_sub(draw, quoted_b, text_max_w, start_size=36, min_size=22, max_lines=3)
    sub_font_size = min(sub_font_a.size, sub_font_b.size)
    sub_font = load_font(sub_font_size)
    # 폰트 크기를 맞췄으니 줄바꿈도 그 크기 기준으로 다시 계산 (명시적 \n 우선)
    lines_a = split_and_wrap(draw, quoted_a, sub_font, text_max_w)
    lines_b = split_and_wrap(draw, quoted_b, sub_font, text_max_w)

    centered_multiline(draw, box_a, option_a, lines_a, main_font, sub_font,
                        (255, 255, 255), (255, 235, 232), block_gap=46)
    centered_multiline(draw, box_b, option_b, lines_b, main_font, sub_font,
                        (255, 255, 255), (225, 232, 255), block_gap=46)

    # 중앙 VS 배지
    badge_r = 56
    badge_cx, badge_cy = W / 2, box_top + box_h / 2
    badge_box = [(badge_cx - badge_r, badge_cy - badge_r), (badge_cx + badge_r, badge_cy + badge_r)]
    shadow_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow_layer)
    sd.ellipse([(badge_box[0][0], badge_box[0][1] + 6), (badge_box[1][0], badge_box[1][1] + 6)],
               fill=(0, 0, 0, 60))
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(10))
    img.alpha_composite(shadow_layer)

    draw = ImageDraw.Draw(img)
    draw.ellipse(badge_box, fill=(255, 255, 255, 255), outline=(235, 235, 235, 255), width=2)
    vb = draw.textbbox((0, 0), "VS", font=vs_font)
    vw, vh = vb[2] - vb[0], vb[3] - vb[1]
    draw.text((badge_cx - vw / 2, badge_cy - vh / 2 - vb[1]), "VS", font=vs_font, fill=TEXT_DARK)

    # 하단 워터마크
    wm = f"{handle}  ·  밸런스게임연구소"
    wb = draw.textbbox((0, 0), wm, font=watermark_font)
    ww = wb[2] - wb[0]
    draw.text(((W - ww) / 2, box_top + box_h + 40), wm, font=watermark_font, fill=MUTED)

    img.convert("RGB").save(out_path, "PNG")
    return out_path


def make_text_slide(text: str, out_path: str, slide_no: int = None, slide_total: int = None,
                     handle: str = "@pick1_daily", eyebrow: str = "오늘의 밸런스게임"):
    """Instagram 캐러셀용 서사(narrative) 텍스트 슬라이드 카드를 렌더링한다.
    카드 이미지와 동일한 브랜드 톤(배경색/상단 라벨/워터마크)을 유지하고,
    가운데에 텍스트를 자동 줄바꿈 + 자동 폰트 크기 조정으로 배치한다."""
    W, H = 1080, 1080
    img = Image.new("RGBA", (W, H), BG_COLOR + (255,))
    draw = ImageDraw.Draw(img)

    brand_font = load_font(38)
    watermark_font = load_font(26)

    # 상단 브랜드 라벨
    eyebrow_bb = draw.textbbox((0, 0), eyebrow, font=brand_font)
    eyebrow_w = eyebrow_bb[2] - eyebrow_bb[0]
    draw.text(((W - eyebrow_w) / 2, 84), eyebrow, font=brand_font, fill=(70, 70, 75))
    draw.line([(W / 2 - 40, 140), (W / 2 + 40, 140)], fill=(220, 120, 110), width=4)

    # 우상단 슬라이드 번호 배지 (예: 1/3) - 스와이프 유도
    if slide_no and slide_total:
        badge = f"{slide_no}/{slide_total}"
        bb = draw.textbbox((0, 0), badge, font=brand_font)
        bw = bb[2] - bb[0]
        draw.text((W - bw - 64, 84), badge, font=brand_font, fill=(180, 180, 185))

    # 중앙 텍스트: 자동 줄바꿈 + 자동 폰트 크기 조정
    max_w = W - 160
    font, lines = fit_wrapped_sub(draw, text, max_w, start_size=64, min_size=32, max_lines=9)

    line_metrics = []
    total_h = 0
    line_gap = 16
    for line in lines:
        lb = draw.textbbox((0, 0), line, font=font)
        lh = lb[3] - lb[1]
        line_metrics.append((lh, lb[1]))
        total_h += lh
    total_h += line_gap * max(len(lines) - 1, 0)

    top = (H - total_h) / 2 + 30
    y = top
    for line, (lh, ltop) in zip(lines, line_metrics):
        lb = draw.textbbox((0, 0), line, font=font)
        lw = lb[2] - lb[0]
        draw.text(((W - lw) / 2, y - ltop), line, font=font, fill=TEXT_DARK)
        y += lh + line_gap

    # 하단 워터마크
    wm = f"{handle}  ·  밸런스게임연구소"
    wb = draw.textbbox((0, 0), wm, font=watermark_font)
    ww = wb[2] - wb[0]
    draw.text(((W - ww) / 2, H - 100), wm, font=watermark_font, fill=MUTED)

    img.convert("RGB").save(out_path, "PNG")
    return out_path


if __name__ == "__main__":
    # 로컬 테스트용 샘플 카드 생성
    make_vs_card("신라면파", "땀 뻘뻘 흘리면서\n먹어야 라면 각이지 ㅋㅋ!",
                 "진라면파", "자극 없는 깔끔한 국물이\n진짜 찐이지!",
                 "sample_card.png")
    make_text_slide("새벽 5시 알람을 열 번 넘게 끄고서야 겨우 일어나면서도, 또 이 짓을 반복하고 있는 나 자신이 새삼 한심하게 느껴짐.",
                     "sample_slide1.png", slide_no=1, slide_total=3)
