"""Create the sample media files locally, with no download.

    python3 make_samples.py

Writes into samples/ :
    screen_4k.png      3840x2160, a plain gradient standing in for a screenshot
    photo_portrait.png 1536x2048, a portrait aspect ratio
    utterance_8s.wav   8 seconds, 16kHz mono
    call_600s.wav       600 seconds, 16kHz mono  (skipped unless --long)

Generated rather than shipped so the handout zip stays small and nothing has
to be fetched over the venue wifi.
"""

import math
import os
import struct
import sys
import wave
import zlib

SAMPLES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "samples")


def write_png(path, width, height):
    """Write an RGB PNG with a cheap vertical gradient, stdlib only."""
    raw = bytearray()
    for y in range(height):
        shade = int(255 * y / float(max(1, height - 1)))
        row = bytes(bytearray([shade // 3, shade // 2, shade])) * width
        raw.append(0)                  # filter type 0 for this scanline
        raw.extend(row)

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", ihdr)
           + chunk(b"IDAT", zlib.compress(bytes(raw), 6))
           + chunk(b"IEND", b""))

    with open(path, "wb") as fh:
        fh.write(png)
    return len(png)


def write_wav(path, seconds, rate=16000, freq=220.0):
    """Write a quiet mono tone so the file is a valid, readable WAV."""
    frames = int(seconds * rate)
    buf = bytearray()
    for n in range(frames):
        value = int(3000 * math.sin(2.0 * math.pi * freq * n / rate))
        buf += struct.pack("<h", value)
    with wave.open(path, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(bytes(buf))
    return os.path.getsize(path)


def main(verbose=True, want_long=None):
    if want_long is None:
        want_long = "--long" in sys.argv
    if not os.path.isdir(SAMPLES_DIR):
        os.makedirs(SAMPLES_DIR)

    jobs = [
        ("screen_4k.png", lambda p: write_png(p, 3840, 2160)),
        ("photo_portrait.png", lambda p: write_png(p, 1536, 2048)),
        ("utterance_8s.wav", lambda p: write_wav(p, 8)),
    ]
    if want_long:
        jobs.append(("call_600s.wav", lambda p: write_wav(p, 600)))

    for name, build in jobs:
        path = os.path.join(SAMPLES_DIR, name)
        size = build(path)
        if verbose:
            print("wrote %-20s %8.1f KB" % (name, size / 1024.0))

    if verbose:
        if not want_long:
            print("\n(run with --long to also write a 600s WAV, about 19 MB)")
        print("\nSamples ready in %s" % SAMPLES_DIR)


if __name__ == "__main__":
    main()
