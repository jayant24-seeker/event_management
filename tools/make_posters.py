"""Generate original placeholder posters (portrait) and hero banners (wide) as SVG.

Run:  python tools/make_posters.py
Real event artwork from organizers replaces these later.
"""
import json
import math
from datetime import datetime
from pathlib import Path

APP = Path(__file__).resolve().parent.parent / "app"
ROOT = APP / "static"
EVENTS = json.loads((APP / "data" / "events.json").read_text(encoding="utf-8"))

# slug -> (background top, background bottom, accent, light, motif)
STYLES = {
    "jaipur-night-run-2026": ("#2B0A3D", "#D6246E", "#FFB627", "#FFF4E6", "rays"),
    "kota-campus-beats": ("#0B1E3F", "#2F5BEA", "#FF5DA2", "#F2F6FF", "rings"),
    "jodhpur-blue-city-cyclothon": ("#08304A", "#2C8FC9", "#FFD166", "#EAF7FF", "arches"),
    "chandigarh-startup-mixer": ("#101418", "#1F6F5C", "#B8F35C", "#F2FFF6", "grid"),
    "surat-street-food-fest": ("#7A1E0E", "#F06A1D", "#FFE08A", "#FFF7EA", "waves"),
    "ajmer-sufi-evening": ("#1B1033", "#7C3AED", "#F7C873", "#FBF5FF", "arches"),
    "jaipur-blue-pottery-workshop": ("#0E2A5C", "#3D7BD9", "#F4F1E8", "#F4F1E8", "rings"),
    "kota-standup-night": ("#1A1A1A", "#E23B3B", "#FFE14D", "#FFFFFF", "rays"),
}


def motif(kind, w, h, accent, light):
    cx, cy = w * 0.62, h * 0.38
    parts = []
    if kind == "rays":
        for i in range(18):
            a = math.radians(i * 20)
            x2, y2 = cx + math.cos(a) * w * 1.4, cy + math.sin(a) * w * 1.4
            a2 = math.radians(i * 20 + 8)
            x3, y3 = cx + math.cos(a2) * w * 1.4, cy + math.sin(a2) * w * 1.4
            parts.append(f'<polygon points="{cx:.0f},{cy:.0f} {x2:.0f},{y2:.0f} {x3:.0f},{y3:.0f}" fill="{light}" opacity="0.07"/>')
        parts.append(f'<circle cx="{cx:.0f}" cy="{cy:.0f}" r="{min(w, h) * 0.22:.0f}" fill="{accent}"/>')
    elif kind == "rings":
        for i in range(9, 0, -1):
            r = min(w, h) * 0.06 * i
            parts.append(f'<circle cx="{cx:.0f}" cy="{cy:.0f}" r="{r:.0f}" fill="none" stroke="{accent if i % 3 == 0 else light}" stroke-width="{10 if i % 3 == 0 else 3}" opacity="{0.9 if i % 3 == 0 else 0.25}"/>')
    elif kind == "arches":
        aw = w / 5
        for row in range(3):
            for i in range(6):
                x = i * aw - (aw / 2 if row % 2 else 0)
                y = h * 0.12 + row * aw * 1.25
                parts.append(
                    f'<path d="M{x:.0f},{y + aw * 1.1:.0f} V{y + aw * 0.5:.0f} Q{x:.0f},{y:.0f} {x + aw / 2:.0f},{y - aw * 0.15:.0f} '
                    f'Q{x + aw:.0f},{y:.0f} {x + aw:.0f},{y + aw * 0.5:.0f} V{y + aw * 1.1:.0f}" fill="none" '
                    f'stroke="{accent if (row + i) % 4 == 0 else light}" stroke-width="5" opacity="{0.85 if (row + i) % 4 == 0 else 0.22}"/>'
                )
    elif kind == "grid":
        step = w / 14
        for gx in range(15):
            for gy in range(int(h / step) + 1):
                d = math.hypot(gx * step - cx, gy * step - cy)
                r = max(2, 14 - d / (w / 14))
                parts.append(f'<circle cx="{gx * step:.0f}" cy="{gy * step:.0f}" r="{r:.1f}" fill="{accent}" opacity="0.8"/>')
    elif kind == "waves":
        for i in range(10):
            y = h * 0.1 + i * h * 0.06
            amp = h * 0.03
            d = f"M0,{y:.0f} " + " ".join(
                f"Q{x + w / 16:.0f},{y - amp if (x // (w / 8)) % 2 == 0 else y + amp:.0f} {x + w / 8:.0f},{y:.0f}"
                for x in [k * w / 8 for k in range(8)]
            )
            parts.append(f'<path d="{d}" fill="none" stroke="{accent if i % 3 == 0 else light}" stroke-width="{9 if i % 3 == 0 else 3}" opacity="{0.9 if i % 3 == 0 else 0.3}"/>')
    return "\n  ".join(parts)


def svg(w, h, style, text=""):
    top, bottom, accent, light, kind = style
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="0.3" y2="1">
      <stop offset="0" stop-color="{top}"/><stop offset="1" stop-color="{bottom}"/>
    </linearGradient>
    <filter id="grain"><feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" stitchTiles="stitch"/><feColorMatrix values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 0.08 0"/></filter>
  </defs>
  <rect width="{w}" height="{h}" fill="url(#bg)"/>
  {motif(kind, w, h, accent, light)}
  <rect width="{w}" height="{h}" filter="url(#grain)"/>
  {text}
</svg>
'''


def poster_text(e, w, h, accent, light):
    start = datetime.fromisoformat(e["start"])
    words = e["title"].upper().split()
    lines, cur = [], ""
    for word in words:
        if len(cur) + len(word) > 11 and cur:
            lines.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}".strip()
    lines.append(cur)
    size = 108 if max(len(l) for l in lines) <= 9 else 92
    y0 = h - 200 - (len(lines) - 1) * size
    font = "font-family=\"Bricolage Grotesque, Arial Black, Helvetica, sans-serif\""
    title = "".join(
        f'<text x="60" y="{y0 + i * size:.0f}" {font} font-weight="800" font-size="{size}" fill="{light}" letter-spacing="-2">{l}</text>'
        for i, l in enumerate(lines)
    )
    meta = (
        f'<rect x="60" y="{h - 150}" width="{w - 120}" height="3" fill="{accent}"/>'
        f'<text x="60" y="{h - 92}" {font} font-weight="700" font-size="40" fill="{accent}">{start:%d %b %Y}</text>'
        f'<text x="{w - 60}" y="{h - 92}" text-anchor="end" {font} font-weight="700" font-size="40" fill="{light}">{e["city"].upper()}</text>'
        f'<text x="60" y="110" {font} font-weight="700" font-size="30" fill="{light}" opacity="0.85" letter-spacing="6">{e["category"].upper()}</text>'
    )
    return title + meta


def main():
    for e in EVENTS:
        style = STYLES[e["slug"]]
        _, _, accent, light, _ = style
        (ROOT / e["poster"]).write_text(svg(900, 1200, style, poster_text(e, 900, 1200, accent, light)), encoding="utf-8")
        (ROOT / e["banner"]).write_text(svg(1600, 900, style), encoding="utf-8")
        print("wrote", e["slug"])


if __name__ == "__main__":
    main()
