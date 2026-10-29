"""Exercise 1: what does one image cost your agent?

Run it on the sample, then run it on a screenshot of your own screen.

    python3 ex1_image.py
    python3 ex1_image.py samples/screen_4k.png
    python3 ex1_image.py ~/Desktop/my_screenshot.png
    python3 ex1_image.py --size 1920x1080

Three questions to answer before you move on:
    1. Which preset is cheapest for your image, and by what factor?
    2. Shrink your image by half in any image editor and run it again.
       Which presets changed, and which did not?
    3. In the staircase at the bottom of the output, find two widths 80 pixels
       apart that differ by 512 tokens. Why can that happen?
"""

import os
import re
import sys
import textwrap

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)          # run correctly from any directory

import models
import tokenbill

# A page of dense prose is roughly this many characters.
CHARS_PER_PAGE = 3000
DEFAULT_IMAGE = os.path.join(HERE, "samples", "screen_4k.png")


def parse_args(argv):
    """Accept either an image path or --size WxH (equals sign or space)."""
    path = None
    size = None
    args = list(argv[1:])
    while args:
        arg = args.pop(0)
        if arg in ("-h", "--help"):
            print(__doc__)
            sys.exit(0)
        if arg == "--size":
            text = args.pop(0) if args else ""
            # Unquoted "1920 x 1080" arrives as three arguments: put it back
            # together, but never swallow a following file name or flag.
            while args and not re.search(r"\d\D+\d", text) \
                    and re.fullmatch(r"[\dxX\u00d7*]+", args[0]):
                text += args.pop(0)
            size = _parse_size(text)
        elif arg.startswith("--size="):
            size = _parse_size(arg.split("=", 1)[1])
        elif not arg.startswith("-") and path is None:
            path = arg
    return path, size


def _parse_size(value):
    """Parse 1920x1080, tolerating spaces, X, the multiplication sign and *."""
    cleaned = value.lower().replace("\u00d7", "x").replace("*", "x").replace(" ", "")
    try:
        width, height = cleaned.split("x")
        width, height = int(width), int(height)
        if width <= 0 or height <= 0:
            raise ValueError
    except ValueError:
        sys.exit("Could not read a size from %r. Use WIDTHxHEIGHT, for example:\n"
                 "  python3 ex1_image.py --size 1920x1080" % value)
    return width, height


def resolve(path, size):
    """Return (width, height, label) from a file, an explicit size, or the sample."""
    if size:
        return size[0], size[1], "--size %dx%d" % size
    if path is None:
        path = DEFAULT_IMAGE
    try:
        width, height = tokenbill.image_size(path)
    except Exception as exc:                      # missing, HEIC, truncated, not an image
        print("Cannot read %s as an image (%s)." % (path, exc))
        print("Use a PNG, JPEG, GIF or BMP, run  python3 make_samples.py  to create")
        print("the samples, or pass a size directly:  python3 ex1_image.py --size 1920x1080")
        sys.exit(1)
    return width, height, path


def main():
    path, size = parse_args(sys.argv)
    width, height, label = resolve(path, size)
    pixels = width * height

    print()
    print("IMAGE: %s" % label)
    print("%d x %d px = %s pixels, aspect %.2f"
          % (width, height, tokenbill.human(pixels), width / float(height)))
    print()
    def row(preset, result):
        print("%-31s %7s  %s"
              % (preset["plain"], tokenbill.human(result["tokens"]), result["detail"]))

    print("%-31s %7s  %s" % ("MODELLED STRATEGIES", "tokens", "how it got there"))
    print("-" * 78)
    results = {}
    for name, preset in models.IMAGE_PRESETS.items():
        results[name] = tokenbill.image_tokens(preset, width, height)
        row(preset, results[name])

    cheapest = min(results.items(), key=lambda kv: kv[1]["tokens"])
    dearest = max(results.items(), key=lambda kv: kv[1]["tokens"])
    spread = dearest[1]["tokens"] / float(cheapest[1]["tokens"])
    print("-" * 78)
    print("Spread: %.1fx for the same picture, cheapest to dearest." % spread)

    print()
    print("%-31s %7s  %s" % ("REAL PRODUCTS (published rules)", "tokens", "how it got there"))
    print("-" * 78)
    for name, preset in models.PUBLISHED_IMAGE_PRESETS.items():
        row(preset, tokenbill.image_tokens(preset, width, height))
    print("-" * 78)
    print(textwrap.fill("Vendor rules change by model generation. Re-check the "
                        "docs page before quoting.", 78))

    pages = dearest[1]["tokens"] / float(tokenbill.text_tokens(CHARS_PER_PAGE))
    print("At the dearest modelled strategy this image costs about %.1f pages "
          "of prose." % pages)

    print()
    print("THE TILE CLIFF: tiled-448 near your image's aspect ratio")
    print("-" * 78)
    tiled = models.IMAGE_PRESETS["tiled-448"]
    base = width
    for delta in (-240, -120, -40, 0, 40, 120, 240):
        probe_w = max(64, base + delta)
        result = tokenbill.image_tokens(tiled, probe_w, height)
        marker = "  <- your image" if delta == 0 else ""
        print("%5d x %-5d px   grid %dx%-2d   %6s tokens%s"
              % (probe_w, height, result["grid"][0], result["grid"][1],
                 tokenbill.human(result["tokens"]), marker))

    print()
    print(textwrap.fill("Cost under a tiled encoder is a staircase, not a slope. "
                        "Two images a few pixels apart can sit on different steps.", 78))
    print()
    print(textwrap.fill("NOTE: %s" % models.provenance_note(), 78))
    print()


if __name__ == "__main__":
    main()
