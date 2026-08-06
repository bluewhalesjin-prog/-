"""
카드 이미지 생성 (Pillow). GitHub Actions에서 fonts-noto-cjk 설치가 선행되어야 함.
"""
import os
from PIL import Image, ImageDraw, ImageFont

FONT_CANDIDATES = [
    os.environ.get("FONT_PATH", ""),
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
]

BG_COLOR = (255, 255, 255)
ACCENT_COLOR = (55, 138, 221)
TEXT_COLOR = (20, 20, 20)
MUTED_COLOR = (100, 100, 100)


def load_font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if path and os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def make_vs_card(option_a: str, option_a_sub: str, option_b: str, option_b_sub: str, out_path: str):
    W, H = 1080, 1080
    img = Image.new("RGB", (W, H), BG_COLOR)
    draw = ImageDraw.Draw(img)

    label_font = load_font(52)
    sub_font = load_font(32)
    vs_font = load_font(44)

    pad = 60
    gap = 24
    box_w = (W - pad * 2 - gap) // 2
    box_top = 300
    box_h = 480

    box_a = [(pad, box_top), (pad + box_w, box_top + box_h)]
    box_b = [(pad + box_w + gap, box_top), (W - pad, box_top + box_h)]

    draw.rounded_rectangle(box_a, radius=24, fill=(230, 241, 251))
    draw.rounded_rectangle(box_b, radius=24, fill=(250, 238, 218))

    def centered_text(box, main, sub):
        cx = (box[0][0] + box[1][0]) / 2
        cy = (box[0][1] + box[1][1]) / 2
        mb = draw.textbbox((0, 0), main, font=label_font)
        mw, mh = mb[2] - mb[0], mb[3] - mb[1]
        sb = draw.textbbox((0, 0), sub, font=sub_font)
        sw = sb[2] - sb[0]
        draw.text((cx - mw / 2, cy - mh - 10), main, font=label_font, fill=ACCENT_COLOR)
        draw.text((cx - sw / 2, cy + 20), sub, font=sub_font, fill=MUTED_COLOR)

    centered_text(box_a, option_a, option_a_sub)
    centered_text(box_b, option_b, option_b_sub)

    vb = draw.textbbox((0, 0), "VS", font=vs_font)
    vw = vb[2] - vb[0]
    draw.text(((W - vw) / 2, box_top + box_h / 2 - 25), "VS", font=vs_font, fill=TEXT_COLOR)

    img.save(out_path, "PNG")
    return out_path
