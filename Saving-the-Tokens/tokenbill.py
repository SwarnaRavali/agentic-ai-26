"""Token accounting for multimodal agents, with zero dependencies.

Pure Python standard library. No pip install, no model download, no network.
Everything here is arithmetic over the tiling and framing rules that vision and
audio encoders actually use, so you can price an agent before you build it.

Image side:
    fixed_grid   one square resize, constant cost  (CLIP / LLaVA-1.5 style)
    anyres       tile the image, cost grows in steps (InternVL style)
    native       resize to a patch multiple under a pixel cap (Qwen2-VL style)

Audio side:
    fixed_window pad to a fixed window, constant cost (Whisper style)
    pooled       frames per second after pooling     (audio LM style)
    codec        frame rate times codebooks          (neural codec style)

The numeric parameters live in models.py, not here, so they can be edited and
cited independently of the arithmetic.
"""

import math
import struct
import wave


# --------------------------------------------------------------------------
# Reading media size without any imaging library
# --------------------------------------------------------------------------

def image_size(path):
    """Return (width, height) in pixels for PNG, JPEG, GIF or BMP.

    Reads the file header only. Raises ValueError on an unrecognised format.
    """
    with open(path, "rb") as fh:
        head = fh.read(32)

        if head[:8] == b"\x89PNG\r\n\x1a\n":
            width, height = struct.unpack(">II", head[16:24])
            return int(width), int(height)

        if head[:2] == b"BM":
            width, height = struct.unpack("<ii", head[18:26])
            return int(width), abs(int(height))

        if head[:4] in (b"GIF8",):
            width, height = struct.unpack("<HH", head[6:10])
            return int(width), int(height)

        if head[:2] == b"\xff\xd8":
            return _jpeg_size(fh)

    raise ValueError(
        "Unrecognised image format: %s. Use PNG, JPEG, GIF or BMP, or pass "
        "--size WxH instead of a file." % path
    )


def _jpeg_size(fh):
    """Walk JPEG segment markers to the start-of-frame header."""
    fh.seek(2)
    sof_markers = set(range(0xC0, 0xD0)) - {0xC4, 0xC8, 0xCC}
    while True:
        byte = fh.read(1)
        if not byte:
            break
        if byte != b"\xff":
            continue
        marker = fh.read(1)
        while marker == b"\xff":          # fill bytes are legal between markers
            marker = fh.read(1)
        if not marker:
            break
        code = marker[0]
        if code in (0xD8, 0x01) or 0xD0 <= code <= 0xD7:
            continue                      # standalone markers carry no length
        length_bytes = fh.read(2)
        if len(length_bytes) < 2:
            break
        length = struct.unpack(">H", length_bytes)[0]
        if code in sof_markers:
            payload = fh.read(5)
            height, width = struct.unpack(">HH", payload[1:5])
            return int(width), int(height)
        fh.seek(length - 2, 1)
    raise ValueError("JPEG has no start-of-frame segment")


def audio_duration(path):
    """Return duration in seconds for an uncompressed WAV file."""
    with wave.open(path, "rb") as wav:
        rate = wav.getframerate()
        if not rate:
            raise ValueError("WAV file reports a zero sample rate: %s" % path)
        return wav.getnframes() / float(rate)


# --------------------------------------------------------------------------
# Image token models
# --------------------------------------------------------------------------

def fixed_grid_tokens(patch_px, image_px, merge=1, **_ignored):
    """Constant cost: the image is squashed to one square of image_px.

    Input resolution is discarded, so a phone photo and a 4K screenshot are
    billed identically.
    """
    side = image_px // (patch_px * merge)
    return {
        "tokens": side * side,
        "tiles": 1,
        "grid": (1, 1),
        "resized_to": (image_px, image_px),
        "detail": "%dx%d patches of %dpx" % (side, side, patch_px * merge),
    }


def anyres_tokens(width, height, patch_px, tile_px, max_tiles,
                  min_tiles=1, downsample=1.0, use_thumbnail=True, **_ignored):
    """Tiled cost: pick a tile grid whose aspect ratio matches the image.

    Cost is a step function of the grid, so two images of similar size can land
    on different tile counts and differ by hundreds of tokens.
    """
    grid = _closest_grid(width, height, tile_px, max_tiles, min_tiles)
    tiles = grid[0] * grid[1]
    if use_thumbnail and tiles != 1:
        tiles += 1                        # a whole-image thumbnail tile is appended
    side = int((tile_px // patch_px) * downsample)
    per_tile = side * side
    return {
        "tokens": tiles * per_tile,
        "tiles": tiles,
        "grid": grid,
        "resized_to": (grid[0] * tile_px, grid[1] * tile_px),
        "detail": "%d tiles x %d tokens" % (tiles, per_tile),
    }


def _closest_grid(width, height, tile_px, max_tiles, min_tiles):
    """Choose (cols, rows) with cols*rows <= max_tiles closest in aspect ratio."""
    candidates = set()
    for total in range(min_tiles, max_tiles + 1):
        for cols in range(1, total + 1):
            for rows in range(1, total + 1):
                if min_tiles <= cols * rows <= max_tiles:
                    candidates.add((cols, rows))

    target = width / float(height)
    best = (1, 1)
    best_gap = float("inf")
    for cols, rows in sorted(candidates, key=lambda g: (g[0] * g[1], g)):
        gap = abs(target - cols / float(rows))
        if gap < best_gap:
            best, best_gap = (cols, rows), gap
        elif gap == best_gap:
            # Tie: prefer the larger grid only if the image can actually fill it.
            if width * height > 0.5 * tile_px * tile_px * cols * rows:
                best = (cols, rows)
    return best


def native_tokens(width, height, patch_px, merge, min_pixels, max_pixels,
                  **_ignored):
    """Native-resolution cost: snap to a patch multiple under a pixel cap.

    Cost tracks the input pixel count continuously until max_pixels clamps it,
    which makes max_pixels the single most useful knob on the image side.
    """
    factor = patch_px * merge
    new_w, new_h = _smart_resize(width, height, factor, min_pixels, max_pixels)
    tokens = (new_w // factor) * (new_h // factor)
    return {
        "tokens": tokens,
        "tiles": 1,
        "grid": (new_w // factor, new_h // factor),
        "resized_to": (new_w, new_h),
        "detail": "%dx%d px, %dpx per token" % (new_w, new_h, factor),
    }


def _smart_resize(width, height, factor, min_pixels, max_pixels):
    """Round both sides to a multiple of factor, then scale into the pixel band."""
    new_w = max(factor, int(round(width / float(factor))) * factor)
    new_h = max(factor, int(round(height / float(factor))) * factor)

    if new_w * new_h > max_pixels:
        scale = math.sqrt((width * height) / float(max_pixels))
        new_w = max(factor, int(math.floor(width / scale / factor)) * factor)
        new_h = max(factor, int(math.floor(height / scale / factor)) * factor)
    elif new_w * new_h < min_pixels:
        scale = math.sqrt(min_pixels / float(width * height))
        new_w = int(math.ceil(width * scale / factor)) * factor
        new_h = int(math.ceil(height * scale / factor)) * factor

    return new_w, new_h


# --------------------------------------------------------------------------
# Audio token models
# --------------------------------------------------------------------------

def fixed_window_audio(seconds, window_s, frames_per_s, stride, **_ignored):
    """Constant cost per window: short clips are padded and billed in full.

    A two second "yes" costs the same as a full window of speech.
    """
    windows = max(1, int(math.ceil(seconds / float(window_s))))
    per_window = int(window_s * frames_per_s / stride)
    return {
        "tokens": windows * per_window,
        "detail": "%d window(s) x %d positions" % (windows, per_window),
        "billed_seconds": windows * window_s,
    }


def pooled_audio(seconds, tokens_per_s, **_ignored):
    """Cost proportional to duration. The dominant case for voice agents."""
    return {
        "tokens": int(math.ceil(seconds * tokens_per_s)),
        "detail": "%.1fs x %g tokens/s" % (seconds, tokens_per_s),
        "billed_seconds": seconds,
    }


def codec_audio(seconds, frame_rate_hz, codebooks, **_ignored):
    """Cost proportional to duration times the number of codebooks kept."""
    frames = int(math.ceil(seconds * frame_rate_hz))
    return {
        "tokens": frames * codebooks,
        "detail": "%d frames x %d codebook(s)" % (frames, codebooks),
        "billed_seconds": seconds,
    }


def claude_patch_tokens(width, height, max_edge, max_tokens, patch_px=28, **_ignored):
    """Published patch rule: one token per 28x28 patch, after a fit-to-limits resize.

    An image is shrunk (aspect preserved) to the largest size whose long edge
    and whose patch count both stay under the limits. Two screens of very
    different size can therefore cost exactly the same: the cap is the bill.
    Resize rule and limits: Anthropic vision docs, "Resolution and token cost".
    """
    def patches(w, h):
        return int(math.ceil(w / float(patch_px))) * int(math.ceil(h / float(patch_px)))

    def fits(w, h):
        return (int(math.ceil(w / float(patch_px))) * patch_px <= max_edge
                and int(math.ceil(h / float(patch_px))) * patch_px <= max_edge
                and patches(w, h) <= max_tokens)

    def resized(w, h):
        if fits(w, h):
            return w, h
        if h > w:
            rh, rw = resized(h, w)
            return rw, rh
        aspect = w / float(h)
        lo, hi = 1, w                     # lo always fits, hi never does
        while lo + 1 < hi:
            mid = (lo + hi) // 2
            if fits(mid, max(int(round(mid / aspect)), 1)):
                lo = mid
            else:
                hi = mid
        return lo, max(int(round(lo / aspect)), 1)

    new_w, new_h = resized(width, height)
    return {
        "tokens": patches(new_w, new_h),
        "tiles": 1,
        "grid": (1, 1),
        "resized_to": (new_w, new_h),
        "detail": "resized to %dx%d, %d-px patches" % (new_w, new_h, patch_px),
    }


def openai_tile_tokens(width, height, base_tokens, tile_tokens, tile_px=512,
                       fit_px=2048, short_side_px=768, **_ignored):
    """Published tile rule (high detail): fit in 2048, short side to 768, 512px tiles.

    Cost is base + per-tile * tiles. Source: OpenAI images-and-vision guide,
    GPT-4o / GPT-4.1 section.
    """
    w, h = float(width), float(height)
    scale = min(1.0, fit_px / max(w, h))
    w, h = w * scale, h * scale
    if min(w, h) > short_side_px:
        scale = short_side_px / min(w, h)
        w, h = w * scale, h * scale
    w, h = int(w), int(h)                 # the other side is rounded down
    cols = int(math.ceil(w / float(tile_px)))
    rows = int(math.ceil(h / float(tile_px)))
    return {
        "tokens": base_tokens + tile_tokens * cols * rows,
        "tiles": cols * rows,
        "grid": (cols, rows),
        "resized_to": (w, h),
        "detail": "%d tiles x %d + %d base" % (cols * rows, tile_tokens, base_tokens),
    }


# --------------------------------------------------------------------------
# Dispatch
# --------------------------------------------------------------------------

_IMAGE_KINDS = {
    "fixed_grid": fixed_grid_tokens,
    "anyres": anyres_tokens,
    "native": native_tokens,
    "claude_patch": claude_patch_tokens,
    "openai_tile": openai_tile_tokens,
}

_AUDIO_KINDS = {
    "fixed_window": fixed_window_audio,
    "pooled": pooled_audio,
    "codec": codec_audio,
}


def image_tokens(preset, width, height, **overrides):
    """Price one image under a preset from models.IMAGE_PRESETS."""
    params = dict(preset["params"])
    params.update(overrides)
    fn = _IMAGE_KINDS[preset["kind"]]
    if preset["kind"] == "fixed_grid":
        result = fn(**params)
    else:
        result = fn(width=width, height=height, **params)
    result["tokens"] += preset.get("extra_tokens", 0)
    result["preset"] = preset["name"]
    return result


def audio_tokens(preset, seconds, **overrides):
    """Price one audio clip under a preset from models.AUDIO_PRESETS."""
    params = dict(preset["params"])
    params.update(overrides)
    result = _AUDIO_KINDS[preset["kind"]](seconds=seconds, **params)
    result["tokens"] += preset.get("extra_tokens", 0)
    result["preset"] = preset["name"]
    return result


# About 150 words a minute of ordinary speech, at ~6.5 characters a word.
SPEECH_CHARS_PER_SECOND = 16.25


def text_tokens(characters):
    """Crude text estimate at four characters per token.

    Deliberately crude. The point of this session is that text is rarely where
    your budget goes, so a rough number is enough to make the comparison.
    """
    return int(math.ceil(characters / 4.0))


def human(n):
    """Format a token count with thousands separators."""
    return "{:,}".format(int(n))
