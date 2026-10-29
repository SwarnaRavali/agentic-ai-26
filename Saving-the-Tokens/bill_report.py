"""Take-home: read YOUR agent's real per-call token log and see what dominates.

    python3 bill_report.py my_usage.csv
    python3 bill_report.py sample_usage.csv          # a made-up example
    python3 bill_report.py my_usage.csv --cache-read-multiple 0.1

One CSV row per model call, in order. Columns (extra columns are ignored):

    input_tokens          tokens sent on the call. If you do NOT use prompt
                          caching this is the whole prompt.
    output_tokens         tokens the model produced
    turn          optional  1, 2, 3 ... restarting at 1 starts a new session
    session       optional  any id; overrides the turn-restart rule
    cache_read_tokens     optional  prompt tokens served from the cache
    cache_creation_tokens optional  prompt tokens written to the cache
    new_tokens            optional  tokens in this call's prompt that were NOT in
                          any earlier prompt (on call 1 that is the whole prompt).
                          Log this if you ever drop or replace old items, such as
                          keeping one live screenshot: it is the only way to get
                          an exact "sent again" share after pruning.

Keep each session's rows together and in order. With no turn or session column
the whole file is treated as ONE session.

Using prompt caching? Log the cache columns too. Some providers report
input_tokens WITHOUT the cached part (Anthropic does); then the prompt is
input + cache_read + cache_creation, which is what this script uses when the
cache columns exist. Others (OpenAI) already include cached tokens in the
prompt count and report a cached subset: name that column cached_tokens and
log the prompt count as prompt_tokens.

It answers the session's two questions on your numbers: how much of what you
paid for was content you had already sent, and whether a big fixed prefix or a
growing conversation dominates. It says so plainly when your log cannot
support a verdict (history that shrinks, caches it cannot see). Nothing is
sent anywhere.
"""

import csv
import os
import sys
import textwrap


def num(row, key, line):
    value = (row.get(key) or "").strip()
    if value == "":
        return 0.0
    try:
        return float(value)
    except ValueError:
        sys.exit("Line %d: %r in column %s is not a number." % (line, value, key))


def load(path):
    try:
        with open(path) as handle:
            reader = csv.DictReader(handle)
            cols = [c.strip() for c in (reader.fieldnames or [])]
            rows = list(reader)
    except (UnicodeDecodeError, csv.Error):
        sys.exit("%s does not look like a CSV text file. Export your token log "
                 "as CSV with a header row." % os.path.basename(path))
    if not rows:
        sys.exit("The file has no rows.")
    has = lambda c: c in cols
    if not (has("prompt_tokens") or has("input_tokens")):
        sys.exit("Need a column called input_tokens (or prompt_tokens). Found: %s. "
                 "See the top of this file." % ", ".join(cols))
    calls = []
    session, previous_turn = 0, None
    for i, row in enumerate(rows, start=2):
        row = dict((k.strip(), v) for k, v in row.items() if k)
        read = num(row, "cache_read_tokens", i)
        create = num(row, "cache_creation_tokens", i)
        if has("prompt_tokens"):
            prompt = num(row, "prompt_tokens", i)
            cached = num(row, "cached_tokens", i) or read
        else:
            prompt = num(row, "input_tokens", i) + read + create
            cached = read
        out = num(row, "output_tokens", i)
        if has("session"):
            sid = row.get("session", "")
        else:
            turn = num(row, "turn", i) if has("turn") else None
            if turn is not None and previous_turn is not None and turn <= previous_turn:
                session += 1
            previous_turn = turn
            sid = session
        calls.append({"session": sid, "prompt": prompt, "cached": cached, "out": out,
                      "new": (num(row, "new_tokens", i)
                              if (row.get("new_tokens") or "").strip() != "" else None)})
    sessions = {}
    for call in calls:
        sessions.setdefault(call["session"], []).append(call)
    return calls, list(sessions.values()), has("cache_read_tokens") or has("cached_tokens")


def analyse(sessions):
    total = new = shrinks = replies_like = diffs_n = 0
    grown, firsts, growths, lasts = [], [], [], []
    usable = 0
    for calls in sessions:
        p = [c["prompt"] for c in calls]
        if len(p) < 2:
            continue
        usable += 1
        diffs = [p[t] - p[t - 1] for t in range(1, len(p))]
        shrinks += sum(1 for d in diffs if d < -0.02 * p[0])
        total += sum(p)
        if all(c["new"] is not None for c in calls):
            new += sum(c["new"] for c in calls)
        else:
            new += p[0] + sum(max(0.0, d) for d in diffs)
        for t, d in enumerate(diffs, start=1):
            diffs_n += 1
            out_prev = calls[t - 1]["out"]
            if out_prev and abs(d - out_prev) <= 0.2 * out_prev:
                replies_like += 1
        firsts.append(p[0])
        growths.append(sum(max(0.0, d) for d in diffs) / len(diffs))
        lasts.append(p[-1])
        grown.append((p[-1] - p[0]) / p[-1] if p[-1] else 0.0)
    return {"sessions": usable, "total": total, "reply_only_share":
            (replies_like / float(diffs_n)) if diffs_n else 0.0,
            "exact_new": all(c["new"] is not None for calls in sessions for c in calls), "new": new, "resent": total - new,
            "shrinks": shrinks, "first": sum(firsts) / len(firsts) if firsts else 0.0,
            "growth": sum(growths) / len(growths) if growths else 0.0,
            "last": sum(lasts) / len(lasts) if lasts else 0.0,
            "grown_share": sum(grown) / len(grown) if grown else 0.0}


def main():
    args = sys.argv[1:]
    if "-h" in args or "--help" in args:
        print(__doc__)
        return
    mult = 0.1
    if "--cache-read-multiple" in args:
        i = args.index("--cache-read-multiple")
        try:
            mult = float(args[i + 1])
        except (IndexError, ValueError):
            sys.exit("--cache-read-multiple needs a number, for example 0.1")
        del args[i:i + 2]
    if len(args) != 1:
        sys.exit("usage: python3 bill_report.py usage.csv [--cache-read-multiple 0.1]")
    path = args[0]
    if not os.path.isfile(path):
        sys.exit("No such file: %s" % path)

    calls, sessions, has_cache = load(path)
    r = analyse(sessions)
    if not r["sessions"]:
        sys.exit("Need at least one session with two or more calls.")
    total_in = sum(c["prompt"] for c in calls)
    cached = sum(c["cached"] for c in calls)
    out = sum(c["out"] for c in calls)
    cost_eq = (total_in - cached) + cached * mult
    f = lambda n: "{:,}".format(int(round(n)))

    print()
    print("YOUR AGENT, from %s" % os.path.basename(path))
    print("-" * 78)
    print("calls                         %10s   (%d session%s)"
          % (f(len(calls)), r["sessions"], "" if r["sessions"] == 1 else "s"))
    print("prompt tokens sent in total   %10s" % f(r["total"]))
    if r["exact_new"]:
        print("(new content taken from your new_tokens column: exact, even with pruning)")
    print("  of which new content        %10s   %5.1f%%"
          % (f(r["new"]), 100.0 * r["new"] / r["total"]))
    print("  of which sent again         %10s   %5.1f%%"
          % (f(r["resent"]), 100.0 * r["resent"] / r["total"]))
    if not r["exact_new"]:
        print("  (an estimate: it assumes history is only appended, never pruned;")
        print("   add a new_tokens column for an exact figure)")
    if has_cache:
        print("billed-equivalent input       %10s   (cache reads at %.2fx)" % (f(cost_eq), mult))
    print("output tokens                 %10s   (priced separately, usually higher)" % f(out))
    print("-" * 78)
    print("first call, on average        %10s tokens" % f(r["first"]))
    print("added per call, on average    %10s tokens" % f(r["growth"]))
    print("last call, on average         %10s tokens" % f(r["last"]))
    print()

    notes = []
    verdict = None
    if r["shrinks"]:
        notes.append("The prompt SHRINKS on %d call(s) (pruning, compaction or a new "
                     "session without a turn column). Then 'sent again' is a lower "
                     "bound and growth is a net number, so this log cannot tell you "
                     "whether a pruning fix worked. Compare the billed totals "
                     "before and after instead." % r["shrinks"])
    elif not has_cache and r["last"] and r["growth"] <= 0.005 * r["last"] and len(calls) >= 5:
        notes.append("The prompt barely grows. If you use prompt caching, your "
                     "provider may be reporting only the UNCACHED part (Anthropic's "
                     "input_tokens does). Add cache_read_tokens and "
                     "cache_creation_tokens columns and re-run.")
    elif (not r["exact_new"] and r["reply_only_share"] > 0.6 and len(calls) >= 5):
        notes.append("The prompt grows only by the size of your own replies. If you "
                     "drop or replace old items (for example keeping one live "
                     "screenshot), 'sent again' above is overstated, because the "
                     "new content each turn is hidden by what you removed. Add a "
                     "new_tokens column to get the exact figure.")
    elif max(len(s) for s in sessions) < 3:
        notes.append("Sessions this short cannot show a trend. Log longer ones.")
    elif has_cache and cached > 0.5 * total_in:
        verdict = ("%.0f%% of your prompt tokens are served from the cache at a "
                   "discount, so sending the history again is cheap for you. Look "
                   "at the billed-equivalent line, and at what is NOT cached "
                   "(new content and anything that changes the prefix)."
                   % (100.0 * cached / total_in))
    else:
        if r["grown_share"] > 0.7:
            verdict = ("By the last call, %.0f%% of the prompt is what the "
                       "conversation added. Shrink what each turn adds, or stop "
                       "sending old turns. Trimming the fixed prompt will do little."
                       % (100 * r["grown_share"]))
        elif r["grown_share"] < 0.3:
            verdict = ("By the last call, only %.0f%% of the prompt is conversation; "
                       "the fixed prefix dominates. Trim it, and cache it if you "
                       "have not." % (100 * r["grown_share"]))
        else:
            verdict = ("By the last call, %.0f%% of the prompt is conversation and "
                       "the rest is the fixed prefix. Both matter; measure which one "
                       "your fix touches before spending a sprint on it."
                       % (100 * r["grown_share"]))
    for text in ([verdict] if verdict else []) + notes:
        print(textwrap.fill(text, 78))
        print()
    print(textwrap.fill(
        "A rule of thumb from usage totals, not a breakdown by item. It assumes "
        "history is only ever appended: if you replace or prune items (for "
        "example keeping one live screenshot), 'sent again' is overstated. To split "
        "growth into screenshots, tool results and replies, log token counts "
        "per item with your provider's token-counting call. Cache write "
        "premiums and expiry are not modelled here.", 78))
    print()


if __name__ == "__main__":
    main()
