"""Link preview images (1200x630 PNG) for WhatsApp, Facebook, X and LinkedIn.

Those apps don't show SVG, and the demo and generated posters are SVG, so each event
gets a PNG card drawn here: its colours, category and city, title, date and price.
Cards are cached on disk and redrawn when the event changes.
"""
import hashlib
import re
from pathlib import Path

from flask import current_app
from PIL import Image, ImageDraw, ImageFont, features

from .posters import style_for

W, H = 1200, 630
FONTS = Path(__file__).parent / "fonts"
LATIN = re.compile(r"^[\x20-\x7E₹–—’·]*$")  # what we can draw without a shaping engine


def font(size, weight="ExtraBold"):
    return ImageFont.truetype(str(FONTS / f"Mukta-{weight}.ttf"), size)


def drawable(text):
    # Devanagari needs text shaping (libraqm). Without it, letters come out in the wrong order.
    return bool(LATIN.match(text or "")) or features.check("raqm")


def wrap(draw, text, fnt, width, max_lines):
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=fnt) <= width:
            line = trial
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        while draw.textlength(lines[-1] + "…", font=fnt) > width and " " in lines[-1]:
            lines[-1] = lines[-1].rsplit(" ", 1)[0]
        lines[-1] += "…"
    return lines


def hex_rgb(value):
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def draw_card(e):
    top, bottom, accent, light = style_for(e.slug)[:4]
    img = Image.new("RGB", (W, H))
    # Diagonal-ish vertical gradient between the poster's two background colours.
    a, b = hex_rgb(top), hex_rgb(bottom)
    grad = ImageDraw.Draw(img)
    for y in range(H):
        t = (y / H) ** 1.3
        grad.line([(0, y), (W, y)], fill=tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3)))
    d = ImageDraw.Draw(img, "RGBA")
    acc, lt = hex_rgb(accent), hex_rgb(light)
    # Rings on the right, like the posters.
    for i, r in enumerate(range(80, 520, 55)):
        d.ellipse([W - 230 - r, H // 2 - r, W - 230 + r, H // 2 + r], outline=acc + (150 - i * 14,), width=4 if i % 2 else 2)
    d.ellipse([W - 300, H // 2 - 70, W - 160, H // 2 + 70], fill=acc + (255,))

    x, width = 72, 720
    eyebrow = f"{e.category} · {e.city}".upper()
    d.text((x, 70), eyebrow if drawable(eyebrow) else e.city.upper(), font=font(30, "SemiBold"), fill=acc)

    title = e.title if drawable(e.title) else f"{e.category} in {e.city}" if drawable(e.category) else e.city
    size = 84
    while True:
        fnt = font(size)
        lines = wrap(d, title, fnt, width, 3)
        if len(lines) <= 2 or size <= 60:
            break
        size -= 8
    y = 118
    for line in lines:
        d.text((x, y), line, font=fnt, fill=lt)
        y += int(size * 1.02)

    when = e.start.strftime("%a, %d %b %Y · %-I:%M %p")
    y += 14
    d.text((x, y + 24), when, font=font(34, "SemiBold"), fill=lt + (230,))
    price = "Sold out" if e.sold_out else "Free" if e.is_free else f"From ₹{e.price_from:,}" if len(e.tickets) > 1 else f"₹{e.price_from:,}"
    pf = font(32, "ExtraBold")
    pw = d.textlength(price, font=pf)
    d.rounded_rectangle([x, y + 86, x + pw + 48, y + 142], radius=28, fill=acc + (255,))
    d.text((x + 24, y + 90), price, font=pf, fill=hex_rgb(top))

    # Brand mark, bottom left.
    d.rounded_rectangle([x, H - 96, x + 48, H - 48], radius=12, fill=(214, 36, 110, 255))
    d.text((x + 13, H - 104), "e", font=font(40), fill=(255, 255, 255))
    d.text((x + 62, H - 100), "eventouse", font=font(36), fill=lt)
    return img


def card_path(e):
    """Draw (once per version of the event) and return the PNG's path."""
    key = hashlib.sha1(repr((e.raw, e.sold_out, e.price_from)).encode()).hexdigest()[:12]
    folder = Path(current_app.instance_path) / "share"
    path = folder / f"{e.slug}-{key}.png"
    if not path.exists():
        folder.mkdir(parents=True, exist_ok=True)
        for old in folder.glob(f"{e.slug}-*.png"):
            if re.fullmatch(rf"{re.escape(e.slug)}-[0-9a-f]{{12}}\.png", old.name):  # not "slug-2026-..."
                old.unlink(missing_ok=True)
        tmp = path.with_suffix(".tmp")
        draw_card(e).save(tmp, "PNG", optimize=True)
        tmp.replace(path)
    return path


def site_card_path():
    """The default preview for pages that aren't an event (homepage, Explore, city pages)."""
    path = Path(current_app.instance_path) / "share" / "site-v2.png"
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (W, H), (26, 20, 35))
    d = ImageDraw.Draw(img, "RGBA")
    for i, r in enumerate(range(80, 640, 60)):
        d.ellipse([W - 150 - r, H // 2 - r, W - 150 + r, H // 2 + r], outline=(255, 182, 39, 150 - i * 12), width=4 if i % 2 else 2)
    d.ellipse([W - 220, H // 2 - 70, W - 80, H // 2 + 70], fill=(214, 36, 110, 255))
    d.rounded_rectangle([72, 72, 152, 152], radius=20, fill=(214, 36, 110, 255))
    d.text((94, 58), "e", font=font(72), fill=(255, 255, 255))
    d.text((172, 66), "eventouse", font=font(64), fill=(255, 248, 240))
    y = 230
    for line in ["Runs, concerts, workshops", "and festivals near you"]:
        d.text((72, y), line, font=font(68), fill=(255, 248, 240))
        y += 76
    d.text((72, y + 30), "Jaipur · Kota · Jodhpur · Ajmer · Surat · Chandigarh", font=font(34, "SemiBold"), fill=(255, 182, 39))
    tmp = path.with_suffix(".tmp")
    img.save(tmp, "PNG", optimize=True)
    tmp.replace(path)
    return path
