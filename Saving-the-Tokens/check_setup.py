"""Run this first. It should finish in under two seconds and print PASS.

    python3 check_setup.py

If it prints PASS, you are ready for the session. Nothing is installed,
nothing is downloaded, and nothing talks to the network.

If it prints FAIL, raise your hand. The number next to each check tells the
mentor exactly where to look.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)          # run correctly from any directory

FAILURES = []


def check(number, description, fn):
    try:
        detail = fn()
    except Exception as exc:
        FAILURES.append((number, description, "%s: %s" % (type(exc).__name__, exc)))
        print("  [%d] FAIL  %s" % (number, description))
        return False
    print("  [%d] ok  %-40s %s" % (number, description, detail))
    return True


def main():
    print()
    print("SETUP CHECK, Saving the Tokens")
    print("-" * 78)

    check(1, "python version is 3.7 or newer",
          lambda: _require_python())
    check(2, "standard library modules import",
          lambda: _require_stdlib())
    check(3, "exercise files are present",
          lambda: _require_files())

    check(4, "sample media exists, created if missing",
          lambda: _require_samples())
    check(5, "image header parsing works", lambda: _check_image())
    check(6, "wav header parsing works", lambda: _check_audio())
    check(7, "token arithmetic agrees with the known answer",
          lambda: _check_arithmetic())

    print("-" * 78)
    if FAILURES:
        print("FAIL: %d check(s) did not pass.\n" % len(FAILURES))
        for number, description, reason in FAILURES:
            print("  [%d] %s\n      %s" % (number, description, reason))
        print()
        sys.exit(1)

    print("PASS. You are ready.")
    print()
    print("Next:  python3 ex1_image.py")
    print()


def _require_python():
    if sys.version_info < (3, 7):
        raise RuntimeError("found %s, need 3.7 or newer"
                           % ".".join(str(v) for v in sys.version_info[:3]))
    return ".".join(str(v) for v in sys.version_info[:3])


def _require_stdlib():
    import math, struct, wave, zlib        # noqa: F401
    return "math, struct, wave, zlib"


def _require_files():
    here = os.path.dirname(os.path.abspath(__file__))
    needed = ["tokenbill.py", "models.py", "ex1_image.py", "ex2_audio.py",
              "ex3_budget.py", "bill_report.py", "make_samples.py"]
    missing = [n for n in needed if not os.path.isfile(os.path.join(here, n))]
    if missing:
        raise RuntimeError("missing: %s" % ", ".join(missing))
    return "%d files" % len(needed)


def _require_samples():
    """Create the sample media if absent, then confirm it is there."""
    needed = ["samples/screen_4k.png", "samples/utterance_8s.wav"]
    if all(os.path.isfile(os.path.join(HERE, n)) for n in needed):
        return "already present"

    import make_samples
    try:
        make_samples.main(verbose=False)
    except (IOError, OSError):
        # A read-only folder (a zip opened in place, a locked laptop) is not a
        # broken machine. Every exercise still runs with --size.
        return "skipped, folder is read-only (use --size)"

    missing = [n for n in needed if not os.path.isfile(os.path.join(HERE, n))]
    if missing:
        raise RuntimeError("could not create: %s" % ", ".join(missing))
    return "created"


def _check_image():
    import tokenbill
    here = os.path.dirname(os.path.abspath(__file__))
    if not os.path.isfile(os.path.join(here, "samples/screen_4k.png")):
        return "skipped, no sample file"
    width, height = tokenbill.image_size(os.path.join(here, "samples/screen_4k.png"))
    if (width, height) != (3840, 2160):
        raise RuntimeError("read %dx%d, expected 3840x2160" % (width, height))
    return "3840x2160"


def _check_audio():
    import tokenbill
    here = os.path.dirname(os.path.abspath(__file__))
    if not os.path.isfile(os.path.join(here, "samples/utterance_8s.wav")):
        return "skipped, no sample file"
    seconds = tokenbill.audio_duration(os.path.join(here, "samples/utterance_8s.wav"))
    if abs(seconds - 8.0) > 0.05:
        raise RuntimeError("read %.3fs, expected 8.0s" % seconds)
    return "8.00 s"


def _check_arithmetic():
    """A fixed 336px square at a 14px patch must be exactly 576 tokens.

    This one is pure geometry with no model-specific assumption, so if it
    disagrees something is genuinely broken rather than merely out of date.
    """
    import models
    import tokenbill
    result = tokenbill.image_tokens(models.IMAGE_PRESETS["fixed-336"], 3840, 2160)
    if result["tokens"] != 576:
        raise RuntimeError("got %d tokens, expected 576" % result["tokens"])
    return "576 tokens"


if __name__ == "__main__":
    main()
