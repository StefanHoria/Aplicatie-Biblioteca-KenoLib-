# generate_installer_images.py
"""
Generează imaginile expertului de instalare (Inno Setup), în identitatea
vizuală KenoLib: albastrul de brand + iconița „carte deschisă” (conturul din
utils.make_logo_icon) + textul „KenoLib” cu fontul Cooper Black.

Produce, în installer\\assets\\:
  - wizard-large.bmp     (164x314)   imaginea mare din stânga paginilor
  - wizard-large-2x.bmp  (328x628)   Bun venit / Finalizare (variantă HiDPI)
  - wizard-small.bmp     (55x58)     iconița din colțul paginilor interioare
  - wizard-small-2x.bmp  (110x116)   (variantă HiDPI)

Rulează:  py -3.14-64 installer\\generate_installer_images.py
Fișierele rezultate sunt versionate în git; rulează scriptul din nou doar dacă
schimbi designul (culori / text / iconiță).
"""

import os

from PIL import Image, ImageDraw, ImageFont

# --- Identitate vizuală (aceleași valori ca în config.py) ---
BRAND_ACCENT = (62, 142, 222)        # #3e8ede
BRAND_ACCENT_DARKER = (36, 90, 147)  # #245a93
WHITE = (255, 255, 255)
SUBTITLE = (219, 234, 254)           # alb-albăstrui pentru subtitlu

ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")

# Geometria iconiței (cutie 32x32), identică cu utils.make_logo_icon.
_LEFT_PAGE = [(16, 8), (5, 10), (5, 25), (16, 27)]
_RIGHT_PAGE = [(16, 8), (27, 10), (27, 25), (16, 27)]
_TEXT_ROWS = (14, 18, 22)


def _font(size, bold_display=True):
    """Cooper Black pentru wordmark; Segoe UI pentru subtitlu. Cu rezerve,
    ca scriptul să nu cadă dacă un font lipsește pe alt calculator."""
    candidates = (
        ["COOPBL.TTF", "segoeuib.ttf", "arialbd.ttf"]
        if bold_display else
        ["segoeui.ttf", "arial.ttf"]
    )
    for name in candidates:
        path = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", name)
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _draw_book(draw, cx, cy, size, color, closed_width, line_width):
    """Desenează iconița „carte deschisă” (doar contur) centrată în (cx, cy)."""
    k = size / 32.0
    ox, oy = cx - size / 2.0, cy - size / 2.0

    def M(points):
        return [(ox + px * k, oy + py * k) for px, py in points]

    for page in (_LEFT_PAGE, _RIGHT_PAGE):
        pts = M(page)
        draw.line(pts + [pts[0]], fill=color, width=closed_width, joint="curve")
    for yy in _TEXT_ROWS:
        (lx1, ly1), (lx2, ly2) = M([(8, yy), (13, yy - 0.5)])
        draw.line([(lx1, ly1), (lx2, ly2)], fill=color, width=line_width)
        (rx1, ry1), (rx2, ry2) = M([(19, yy - 0.5), (24, yy)])
        draw.line([(rx1, ry1), (rx2, ry2)], fill=color, width=line_width)


def _fit_font(text, max_width, start_size, bold_display=True):
    """Cel mai mare font (<= start_size) la care `text` încape în max_width."""
    size = start_size
    while size > 8:
        font = _font(size, bold_display)
        if font.getlength(text) <= max_width:
            return font
        size -= 1
    return _font(8, bold_display)


def make_large(scale):
    W, H = int(164 * scale), int(314 * scale)
    img = Image.new("RGB", (W, H), BRAND_ACCENT)
    draw = ImageDraw.Draw(img)

    # Fundal: gradient vertical, albastru de brand -> variantă mai adâncă.
    for y in range(H):
        t = y / max(1, H - 1)
        r = round(BRAND_ACCENT[0] + (BRAND_ACCENT_DARKER[0] - BRAND_ACCENT[0]) * t)
        g = round(BRAND_ACCENT[1] + (BRAND_ACCENT_DARKER[1] - BRAND_ACCENT[1]) * t)
        b = round(BRAND_ACCENT[2] + (BRAND_ACCENT_DARKER[2] - BRAND_ACCENT[2]) * t)
        draw.line([(0, y), (W, y)], fill=(r, g, b))

    icon = 88 * scale
    _draw_book(
        draw, W / 2, 96 * scale, icon, WHITE,
        closed_width=max(2, round(icon / 16)),
        line_width=max(1, round(icon / 40)),
    )

    wordmark = _fit_font("KenoLib", W - 24 * scale, round(31 * scale))
    draw.text((W / 2, 182 * scale), "KenoLib", font=wordmark, fill=WHITE, anchor="mm")

    # Linie subțire despărțitoare + subtitlu.
    ry = 208 * scale
    draw.line([(W / 2 - 34 * scale, ry), (W / 2 + 34 * scale, ry)],
              fill=SUBTITLE, width=max(1, round(scale)))
    subtitle = _fit_font("Managementul bibliotecii", W - 20 * scale, round(13 * scale), bold_display=False)
    draw.text((W / 2, 224 * scale), "Managementul bibliotecii", font=subtitle,
              fill=SUBTITLE, anchor="mm")
    return img


def make_small(scale):
    W, H = int(55 * scale), int(58 * scale)
    img = Image.new("RGB", (W, H), WHITE)
    draw = ImageDraw.Draw(img)
    icon = 42 * scale
    _draw_book(
        draw, W / 2, H / 2, icon, BRAND_ACCENT,
        closed_width=max(2, round(icon / 14)),
        line_width=max(1, round(icon / 34)),
    )
    return img


def main():
    os.makedirs(ASSETS_DIR, exist_ok=True)
    outputs = {
        "wizard-large.bmp": make_large(1),
        "wizard-large-2x.bmp": make_large(2),
        "wizard-small.bmp": make_small(1),
        "wizard-small-2x.bmp": make_small(2),
    }
    for name, img in outputs.items():
        path = os.path.join(ASSETS_DIR, name)
        img.save(path, "BMP")
        print(f"scris: {path}  ({img.width}x{img.height})")


if __name__ == "__main__":
    main()
