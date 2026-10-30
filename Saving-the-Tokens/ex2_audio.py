"""Exercise 2: what does speech cost your agent?

    python3 ex2_audio.py
    python3 ex2_audio.py samples/utterance_8s.wav
    python3 ex2_audio.py --seconds 600
    python3 ex2_audio.py --seconds 31 --brief      (the first table only)

Three questions to answer before you move on:
    1. Under window-30s, what does a 2 second "yes" cost? What does a 29
       second answer cost? Explain the result to the person next to you.
    2. Your voice agent holds a 10 minute call and both sides are transcribed
       into context. Which preset keeps you inside a 128k window?
    3. Your system prompt is 400 tokens. At pooled-32, how many seconds of
       speech does it take to outweigh the entire prompt?
"""

import os
import sys
import textwrap

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)          # run correctly from any directory

import models
import tokenbill

TEXT_PROMPT_TOKENS = 400
CONTEXT_WINDOW = 128000
DEFAULT_AUDIO = os.path.join(HERE, "samples", "utterance_8s.wav")


BRIEF = False                         # --brief: the first table only


def parse_args(argv):
    global BRIEF
    path = None
    seconds = None
    args = list(argv[1:])
    while args:
        arg = args.pop(0)
        if arg in ("-h", "--help"):
            print(__doc__)
            sys.exit(0)
        if arg == "--brief":
            BRIEF = True
        elif arg == "--seconds":
            seconds = _parse_seconds(args.pop(0) if args else "")
        elif arg.startswith("--seconds="):
            seconds = _parse_seconds(arg.split("=", 1)[1])
        elif not arg.startswith("-") and path is None:
            path = arg
    return path, seconds


def _parse_seconds(value):
    try:
        seconds = float(value)
        if not (0 < seconds < 86400):             # also rejects nan and inf
            raise ValueError
    except ValueError:
        sys.exit("Could not read a duration from %r. Use a number of seconds, "
                 "for example:\n  python3 ex2_audio.py --seconds 8" % value)
    return seconds


def resolve(path, seconds):
    if seconds is not None:
        return seconds, "--seconds %g" % seconds
    if path is None:
        path = DEFAULT_AUDIO
    try:
        return tokenbill.audio_duration(path), path
    except (IOError, OSError, EOFError):
        print("Cannot open %s" % path)
        print("Run  python3 make_samples.py  to create the sample files, or")
        print("pass a duration directly:  python3 ex2_audio.py --seconds 8")
        sys.exit(1)
    except Exception as exc:                      # a compressed or odd WAV
        print("Cannot read %s as uncompressed WAV (%s)." % (path, exc))
        print("Pass a duration instead:  python3 ex2_audio.py --seconds 8")
        sys.exit(1)


def main():
    path, seconds = parse_args(sys.argv)
    seconds, label = resolve(path, seconds)

    print()
    print("AUDIO: %s" % label)
    print("%.2f seconds" % seconds)
    print()
    print("%-33s %7s  %s" % ("strategy", "tokens", "how it got there"))
    print("-" * 78)

    results = {}
    for name, preset in models.AUDIO_PRESETS.items():
        result = tokenbill.audio_tokens(preset, seconds)
        results[name] = result
        print("%-33s %7s  %s"
              % (preset["plain"], tokenbill.human(result["tokens"]), result["detail"]))

    words = tokenbill.text_tokens(seconds * tokenbill.SPEECH_CHARS_PER_SECOND)
    padded = results["window-30s"]["tokens"]
    print("%-33s %7s  the recognised words, as text"
          % ("Send the words, not the sound", tokenbill.human(words)))
    print("-" * 78)
    print("Your 400 token system prompt, for comparison: %s tokens."
          % tokenbill.human(TEXT_PROMPT_TOKENS))
    print("The words as text are %.0fx fewer tokens than speech at 32 a second,"
          % (results["pooled-32"]["tokens"] / float(words)))
    print("and up to %.0fx fewer than a padded window (the worst case)."
          % (padded / float(words)))
    print()

    if BRIEF:
        print("Short version. Leave off --brief to also see the duration sweep, the")
        print("ten minute call and the break-even.")
        return

    print("DURATION SWEEP: tokens as the clip gets longer")
    print("-" * 78)
    header = "%9s" % "seconds"
    for name in models.AUDIO_PRESETS:
        header += " %13s" % name
    print(header)
    for probe in (0.5, 2, 8, 30, 31, 120, 600):
        row = "%9g" % probe
        for preset in models.AUDIO_PRESETS.values():
            row += " %13s" % tokenbill.human(
                tokenbill.audio_tokens(preset, probe)["tokens"])
        print(row)

    print()
    print("THE TEN MINUTE CALL: both sides of a 600 second conversation")
    print("-" * 78)
    for name, preset in models.AUDIO_PRESETS.items():
        one_way = tokenbill.audio_tokens(preset, 600)["tokens"]
        both = one_way * 2
        verdict = "fits" if both < CONTEXT_WINDOW else "OVERFLOWS"
        print("%-16s %10s tokens   %s a %s window"
              % (name, tokenbill.human(both), verdict,
                 tokenbill.human(CONTEXT_WINDOW)))

    print()
    print("BREAK-EVEN: speech needed to outweigh a %d token prompt"
          % TEXT_PROMPT_TOKENS)
    print("-" * 78)
    for name, preset in models.AUDIO_PRESETS.items():
        if preset["kind"] == "fixed_window":
            # Cost does not scale with duration here, so a break-even in
            # seconds is meaningless. Any clip at all pays the full window.
            full = tokenbill.audio_tokens(preset, 0.5)["tokens"]
            print("%-16s %s  (a single half-second clip already costs %s)"
                  % (name, "any clip at all", tokenbill.human(full)))
            continue
        # Measure the rate over a long probe so the per-clip rounding in the
        # model does not distort a one-second sample.
        per_second = tokenbill.audio_tokens(preset, 100.0)["tokens"] / 100.0
        if per_second <= 0:
            continue
        print("%-16s %6.1f seconds of audio"
              % (name, TEXT_PROMPT_TOKENS / per_second))

    print()
    print(textwrap.fill(
        "This is the whole point. Trimming the prompt is a one-off saving "
        "measured in hundreds of tokens. The audio stream is a recurring "
        "cost measured in thousands per minute.", 78))
    print()
    print(textwrap.fill("NOTE: %s" % models.provenance_note(), 78))
    print()


if __name__ == "__main__":
    main()
