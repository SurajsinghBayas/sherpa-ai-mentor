"""App icons and splash screens for Android and iOS, from the desktop app's icon (apps/desktop/icons).

The mascot head is cut out of the icon's blue tile, then placed on the brand blue (icons) or on
the paper background (splash screens). Run from apps/mobile: python3 scripts/icons.py
"""
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent.parent
SOURCE = HERE.parent / "desktop" / "icons" / "app-icon.png"
BLUE, PAPER = (0x2F, 0x80, 0xED, 255), (0xF8, 0xF5, 0xF0, 255)
HEAD_BOX = (221, 257, 803, 736)  # the pixel-art head inside the 1024px icon
RES = HERE / "android" / "app" / "src" / "main" / "res"
DENSITIES = {"mdpi": 1, "hdpi": 1.5, "xhdpi": 2, "xxhdpi": 3, "xxxhdpi": 4}


def head() -> Image.Image:
    img = Image.open(SOURCE).convert("RGBA").crop(HEAD_BOX)
    # the crop's corners still show the blue tile behind the head's rounded outline: clear them
    for corner in ((0, 0), (img.width - 1, 0), (0, img.height - 1), (img.width - 1, img.height - 1)):
        ImageDraw.floodfill(img, corner, (0, 0, 0, 0), thresh=10)
    return img


def place(canvas: Image.Image, img: Image.Image, width_share: float) -> Image.Image:
    w = round(canvas.width * width_share)
    h = round(img.height * w / img.width)
    scaled = img.resize((w, h), Image.NEAREST)  # pixel art: keep the edges hard
    canvas.alpha_composite(scaled, ((canvas.width - w) // 2, (canvas.height - h) // 2))
    return canvas


def tile(size: int, round_mask: bool = False) -> Image.Image:
    img = place(Image.new("RGBA", (size, size), BLUE), head(), 0.58 if round_mask else 0.66)
    if round_mask:
        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
        img.putalpha(mask)
    return img


def splash(w: int, h: int) -> Image.Image:
    canvas = Image.new("RGBA", (w, h), PAPER)
    side = min(w, h)
    return place(canvas, head(), 0.26 * side / w)


def main() -> None:
    for name, scale in DENSITIES.items():
        legacy, fg = round(48 * scale), round(108 * scale)
        tile(legacy).save(RES / f"mipmap-{name}" / "ic_launcher.png")
        tile(legacy, round_mask=True).save(RES / f"mipmap-{name}" / "ic_launcher_round.png")
        # adaptive foreground: the launcher masks to ~66dp of the 108dp canvas, so the head sits well inside
        place(Image.new("RGBA", (fg, fg), (0, 0, 0, 0)), head(), 0.44).save(RES / f"mipmap-{name}" / "ic_launcher_foreground.png")
    (RES / "values" / "ic_launcher_background.xml").write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n<resources>\n    <color name="ic_launcher_background">#2F80ED</color>\n</resources>\n'
    )
    for png in RES.glob("drawable*/splash.png"):
        w, h = Image.open(png).size
        splash(w, h).save(png)

    ios = HERE / "ios" / "App" / "App" / "Assets.xcassets"
    tile(1024).convert("RGB").save(ios / "AppIcon.appiconset" / "AppIcon-512@2x.png")  # iOS icons must be opaque
    for png in (ios / "Splash.imageset").glob("*.png"):
        splash(2732, 2732).convert("RGB").save(png)
    print("icons and splash screens written")


if __name__ == "__main__":
    main()
