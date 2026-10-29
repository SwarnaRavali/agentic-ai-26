"""Encoder parameters, with a provenance note on every entry.

These are the numbers the arithmetic in tokenbill.py runs on. They are kept
here, separately, for one reason: a token estimate is only as trustworthy as
the parameters behind it, and those parameters change between model releases
and even between library versions.

Every preset carries:
    source    where the parameter came from
    status    "documented" if it is published and stable,
              "check"      if you should confirm it for your own stack

Run  python3 models.py  to print the table and see which rows say "check".

If a row is wrong for the model you actually use, edit it. That is not a
workaround, it is the intended workflow: the arithmetic is general, the
constants are yours.
"""

# --------------------------------------------------------------------------
# Image encoders
# --------------------------------------------------------------------------

IMAGE_PRESETS = {
    "fixed-336": {
        "name": "fixed-336",
        "plain": "Squash it to one small square",
        "label": "Fixed square, 336px (CLIP ViT-L/14 style)",
        "kind": "fixed_grid",
        "params": {"patch_px": 14, "image_px": 336, "merge": 1},
        "source": "336px input, 14px patch, no merge. Standard CLIP ViT-L/14 geometry.",
        "status": "documented",
    },
    "tiled-448": {
        "name": "tiled-448",
        "plain": "Cut it into tiles (up to 12)",
        "label": "Tiled 448px, up to 12 tiles plus thumbnail (InternVL style)",
        "kind": "anyres",
        "params": {
            "patch_px": 14,
            "tile_px": 448,
            "max_tiles": 12,
            "min_tiles": 1,
            "downsample": 0.5,
            "use_thumbnail": True,
        },
        "source": "448px tile, 14px patch, pixel unshuffle 0.5, so 256 tokens "
                  "per tile. Tile budget and thumbnail behaviour vary by release.",
        "status": "check",
    },
    "tiled-448-max6": {
        "name": "tiled-448-max6",
        "plain": "Cut it into tiles (up to 6)",
        "label": "Tiled 448px, capped at 6 tiles",
        "kind": "anyres",
        "params": {
            "patch_px": 14,
            "tile_px": 448,
            "max_tiles": 6,
            "min_tiles": 1,
            "downsample": 0.5,
            "use_thumbnail": True,
        },
        "source": "Same geometry as tiled-448 with a lower tile budget. Included "
                  "to show what the tile cap alone buys you.",
        "status": "check",
    },
    "native-1280": {
        "name": "native-1280",
        "plain": "Shrink to a 1,280-token budget",
        "label": "Native resolution, capped near 1280 tokens (Qwen2-VL style)",
        "kind": "native",
        "params": {
            "patch_px": 14,
            "merge": 2,
            "min_pixels": 56 * 56,
            "max_pixels": 28 * 28 * 1280,
        },
        "source": "14px patch with a 2x2 merge gives 28px per output token. The "
                  "min and max pixel band is a processor setting, not a model "
                  "constant, and defaults differ between library versions.",
        "status": "check",
    },
    "native-256": {
        "name": "native-256",
        "plain": "Shrink to a 256-token budget",
        "label": "Native resolution, capped near 256 tokens",
        "kind": "native",
        "params": {
            "patch_px": 14,
            "merge": 2,
            "min_pixels": 56 * 56,
            "max_pixels": 28 * 28 * 256,
        },
        "source": "Same geometry as native-1280 with a tighter pixel cap. This "
                  "is the knob, exposed.",
        "status": "check",
    },
}


# --------------------------------------------------------------------------
# Published formulas (real products)
# --------------------------------------------------------------------------
# Unlike the presets above, these are the vendors' own published rules,
# checked against their documentation on 2026-10-29. Vendors change them
# between model generations, so re-check the page before quoting a number.

PUBLISHED_IMAGE_PRESETS = {
    "claude-standard": {
        "name": "claude-standard",
        "plain": "Claude, standard tier",
        "label": "28px patches, long edge <= 1,568 px, <= 1,568 visual tokens",
        "kind": "claude_patch",
        "params": {"patch_px": 28, "max_edge": 1568, "max_tokens": 1568},
        "source": "Anthropic docs, Vision > Resolution and token cost, and "
                  "Vision coordinates > How Claude resizes and pads images.",
        "status": "documented",
    },
    "claude-hires": {
        "name": "claude-hires",
        "plain": "Claude, high-resolution tier",
        "label": "28px patches, long edge <= 2,576 px, <= 4,784 visual tokens",
        "kind": "claude_patch",
        "params": {"patch_px": 28, "max_edge": 2576, "max_tokens": 4784},
        "source": "Same pages. Applies to the models the docs list as the "
                  "high-resolution tier (Claude 4.7 and later).",
        "status": "documented",
    },
    "openai-tiles": {
        "name": "openai-tiles",
        "plain": "OpenAI GPT-4o/4.1, high detail",
        "label": "85 base + 170 per 512px tile after fit-to-2048 and short side 768",
        "kind": "openai_tile",
        "params": {"base_tokens": 85, "tile_tokens": 170, "tile_px": 512,
                   "fit_px": 2048, "short_side_px": 768},
        "source": "OpenAI images-and-vision guide, GPT-4o and GPT-4.1 "
                  "(tile-based) section. Newer OpenAI models use a 32px "
                  "patch rule instead; this preset is not that one.",
        "status": "documented",
    },
}


# --------------------------------------------------------------------------
# Audio encoders
# --------------------------------------------------------------------------

AUDIO_PRESETS = {
    "window-30s": {
        "name": "window-30s",
        "plain": "Pad every clip to 30 seconds",
        "label": "Fixed 30s window, 1500 encoder positions (Whisper style)",
        "kind": "fixed_window",
        "params": {"window_s": 30.0, "frames_per_s": 100, "stride": 2},
        "source": "30s window at 100 mel frames per second is 3000 frames, "
                  "halved by a stride-2 convolution to 1500 positions.",
        "status": "documented",
    },
    "pooled-25": {
        "name": "pooled-25",
        "plain": "25 tokens per second of speech",
        "label": "Pooled speech tokens, 25 per second (audio LM style)",
        "kind": "pooled",
        "params": {"tokens_per_s": 25.0},
        "source": "A pooling layer on top of a 50 frames per second encoder. "
                  "The exact rate differs per audio LM. CONFIRM FOR YOUR MODEL.",
        "status": "check",
    },
    "pooled-12.5": {
        "name": "pooled-12.5",
        "plain": "12.5 tokens per second of speech",
        "label": "Pooled speech tokens, 12.5 per second",
        "kind": "pooled",
        "params": {"tokens_per_s": 12.5},
        "source": "A more aggressive pooling ratio. Included to show the "
                  "linear trade between rate and cost.",
        "status": "check",
    },
    "codec-75x8": {
        "name": "codec-75x8",
        "plain": "Audio codec, 8 codebooks",
        "label": "Neural codec, 75Hz frames x 8 codebooks",
        "kind": "codec",
        "params": {"frame_rate_hz": 75.0, "codebooks": 8},
        "source": "Typical 24kHz residual codec framing. Frame rate and the "
                  "number of codebooks you keep both vary. CONFIRM.",
        "status": "check",
    },
    "codec-75x2": {
        "name": "codec-75x2",
        "plain": "Audio codec, 2 codebooks",
        "label": "Neural codec, 75Hz frames x 2 codebooks",
        "kind": "codec",
        "params": {"frame_rate_hz": 75.0, "codebooks": 2},
        "source": "The same codec with only the coarse codebooks kept, which "
                  "is a real deployment choice and a 4x saving.",
        "status": "check",
    },
}


def provenance_note():
    """One line naming how many modelled presets still need confirming."""
    unchecked = [p["name"] for p in list(IMAGE_PRESETS.values()) + list(AUDIO_PRESETS.values())
                 if p["status"] == "check"]
    return ("%d of %d presets are marked 'check': %s. Treat their outputs as "
            "the arithmetic of the stated parameters, not as a measurement of "
            "any shipped model."
            % (len(unchecked),
               len(IMAGE_PRESETS) + len(AUDIO_PRESETS),
               ", ".join(unchecked)))


def _print_table():
    for title, presets in (("IMAGE (modelled)", IMAGE_PRESETS),
                           ("IMAGE (published vendor formulas)", PUBLISHED_IMAGE_PRESETS),
                           ("AUDIO", AUDIO_PRESETS)):
        print("\n%s PRESETS" % title)
        print("-" * 78)
        for preset in presets.values():
            flag = "  " if preset["status"] == "documented" else "? "
            print("%s%-16s %s" % (flag, preset["name"], preset["plain"]))
            print("%-18s %s" % ("", preset["label"]))
            print("%-18s %s" % ("", preset["source"]))
    print("\n" + "-" * 78)
    print(provenance_note())


if __name__ == "__main__":
    _print_table()
