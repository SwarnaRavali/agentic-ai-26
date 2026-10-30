"""Exercise 3: price a whole agent session, then find the lever that matters.

Two agents, the same ten fixes.

    screen   a voice agent that also watches the user's screen. Every turn the
             user speaks and a screenshot is taken. This is BASELINE.
    chat     a text agent with a long, detailed system prompt and no pictures.

History is re-sent on every turn, which is what almost every agent framework
does by default.

    python3 ex3_budget.py                 the screen agent
    python3 ex3_budget.py --agent chat    the chat agent
    python3 ex3_budget.py --agent both    both rankings side by side
    python3 ex3_budget.py --turns 10 --prompt 4000 --cache 0.9
                                          change the assumptions and re-rank
                                          (the flags apply to every agent shown)

The script prints the baseline session, then changes exactly one thing at a
time and ranks the savings. Do not guess the ranking. Run it.

Edit BASELINE or CHAT below to match an agent you actually work on.

Questions:
    1. Before you run it: write down which lever you think wins. Keep the note.
    2. Run --agent both. Which fixes change rank, and what did the pictures
       have to do with it?
    3. Which kind of agent is yours, and which row is therefore your fix?
"""

import copy
import os
import sys
import textwrap

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)          # run correctly from any directory

import models
import tokenbill

CONTEXT_WINDOW = 128000     # a common 128k-class window; some models offer 200k or more

BASELINE = {
    "label": "baseline",
    "turns": 20,
    "user_speech_seconds": 8.0,
    "agent_reply_tokens": 120,
    "system_prompt_tokens": 400,
    "screenshot_every_n_turns": 1,     # 1 means a screenshot every single turn
    "screen_size": (1920, 1080),       # a common laptop or monitor
    "image_preset": "native-1280",
    "audio_preset": "pooled-32",
    "keep_last_k_turns": None,         # None means keep the whole history
    "drop_old_images": False,          # keep only the most recent screenshot
    "prefix_cache_discount": 0.0,      # 0.9 means cached tokens cost 10%
    "output_price_multiple": 0.0,      # 0 counts input only; 5 prices output at 5x input
    "transcribe_audio": False,         # send text instead of the audio itself
    "audio_rate_scale": 1.0,           # 0.5 means the speech encoder emits half the tokens
    "transcript_chars_per_second": tokenbill.SPEECH_CHARS_PER_SECOND,   # ~150 words/min
    "screen_as_text": False,           # send a UI tree instead of pixels
    "screen_text_tokens": 300,         # what that tree costs, if you send it
    # Input price per million tokens. Set these to YOUR numbers: they are
    # here to turn tokens into money, not to quote anybody's price list.
    "price_per_million": 3.00,
    "sessions_per_day": 10000,
}


# A text agent: a long, detailed system prompt, longer replies, no pictures.
# The user's message is a typed paragraph, about 100 tokens.
CHAT = dict(BASELINE,
            label="chat",
            system_prompt_tokens=6000,
            agent_reply_tokens=400,
            screenshot_every_n_turns=None,     # None means no screenshots at all
            transcribe_audio=True,
            transcript_chars_per_second=50.0)   # 8 s x 50 = 400 chars, ~100 tokens

AGENTS = {
    "screen": (BASELINE, "a voice agent that also watches a 1920x1080 screen"),
    "chat": (CHAT, "a text agent with a 6,000-token system prompt, no pictures"),
}


def turn_items(config):
    """Token cost of the new content each turn contributes, by type."""
    image_preset = models.IMAGE_PRESETS[config["image_preset"]]
    audio_preset = models.AUDIO_PRESETS[config["audio_preset"]]
    width, height = config["screen_size"]

    if config.get("transcribe_audio"):
        # Speech recognised first, then only the words go to the model. This
        # is the talk's own thesis applied: change the modality, not the size.
        chars = config["user_speech_seconds"] * config["transcript_chars_per_second"]
        audio = tokenbill.text_tokens(chars)
    else:
        audio = tokenbill.audio_tokens(
            audio_preset, config["user_speech_seconds"])["tokens"]
        # Scale the CURRENT encoder, so "halve the speech rate" means exactly
        # that whatever encoder the baseline uses. Swapping to a different
        # preset instead would silently change the encoder family too.
        audio = int(round(audio * config.get("audio_rate_scale", 1.0)))

    if config.get("screen_as_text"):
        image = config["screen_text_tokens"]
    else:
        image = tokenbill.image_tokens(image_preset, width, height)["tokens"]
    return audio, image


def simulate(config):
    """Walk the session turn by turn and total the billed prompt tokens.

    Returns (total_billed, per_turn_rows, final_prompt_size).
    """
    audio_cost, image_cost = turn_items(config)
    system_tokens = config["system_prompt_tokens"] * config.get("system_prompt_scale", 1.0)
    reply_tokens = int(round(config["agent_reply_tokens"] * config.get("agent_reply_scale", 1.0)))
    every = config["screenshot_every_n_turns"]
    every = max(1, every) if every is not None else None
    discount = config["prefix_cache_discount"]

    history = []            # list of (turn_index, kind, tokens)
    rows = []
    total = 0
    previously_billed = []      # the cached prefix, in order

    for turn in range(1, config["turns"] + 1):
        history.append((turn, "audio", audio_cost))
        if every is not None and (turn - 1) % every == 0:
            history.append((turn, "image", image_cost))

        retained = _retain(history, turn, config)

        new_tokens = 0
        cached_tokens = 0
        prefix_intact = True
        for position, item in enumerate(retained):
            key = (item[0], item[1])
            was_there = (position < len(previously_billed)
                         and previously_billed[position] == key)
            if prefix_intact and was_there:
                cached_tokens += item[2]
            else:
                prefix_intact = False      # the cache stops at the first change
                new_tokens += item[2]

        prompt = system_tokens + sum(i[2] for i in retained)
        billed = (system_tokens * (1.0 - discount if turn > 1 else 1.0)
                  + cached_tokens * (1.0 - discount)
                  + new_tokens)
        total += billed + reply_tokens * config.get("output_price_multiple", 0.0)
        previously_billed = [(i[0], i[1]) for i in retained]

        # The reply the model generates this turn becomes history for the next.
        history.append((turn, "reply", reply_tokens))

        rows.append({
            "turn": turn,
            "prompt": int(prompt),
            "billed": int(billed),
            "images": sum(1 for i in retained if i[1] == "image"),
        })

    return int(total), rows, rows[-1]["prompt"]


def _retain(history, current_turn, config):
    """Apply the retention policy to the history list."""
    keep = config["keep_last_k_turns"]
    items = history
    if keep is not None:
        cutoff = current_turn - keep + 1
        items = [i for i in items if i[0] >= cutoff]
    if config["drop_old_images"]:
        last_image_turn = max([i[0] for i in items if i[1] == "image"] or [0])
        items = [i for i in items
                 if i[1] != "image" or i[0] == last_image_turn]
    return items


# Each lever is (name, config change, what it costs you). The third field
# matters: a token saving you would never ship is not a saving.
LEVERS = [
    ("Send a transcript, not the audio",
     {"transcribe_audio": True},
     "needs speech recognition, whose cost, delay and errors are not priced "
     "here; loses tone and overlap"),
    ("Drop stale screenshots, keep the newest",
     {"drop_old_images": True},
     "the agent cannot look back; 2 to 3 images are safer for an agent that "
     "acts, and dropping one every turn breaks a cache (vendors advise batches)"),
    ("Send the screen's text, not pixels",
     {"screen_as_text": True},
     "assumes ~300 tokens of screen text: it saves nothing at 1,222 and costs "
     "more above that; useless for canvases and charts"),
    ("Shrink the image budget 1,280 to 256",
     {"image_preset": "native-256"},
     "the screen becomes a 588x336 view: small text and click targets are "
     "unreadable, so the saving is bought with capability"),
    ("Screenshot every 4th turn",
     {"screenshot_every_n_turns": 4},
     "the agent acts on a screen up to three turns old"),
    ("Keep only the last 5 turns",
     {"keep_last_k_turns": 5},
     "the agent forgets the task unless you pin it; summarising instead costs "
     "a call not priced here; sliding every turn breaks a cache"),
    ("Halve the speech token rate",
     {"audio_rate_scale": 0.5},
     "not a knob an API gives you: it is a property of the audio encoder"),
    ("Halve every agent reply",
     {"agent_reply_scale": 0.5},
     "terser answers; output tokens, usually priced higher, are not counted here"),
    ("Cut the system prompt by 60%",
     {"system_prompt_scale": 0.4},
     "instructions, examples and guardrails: re-test before you ship it"),
    ("Turn on prefix caching (90% off)",
     {"prefix_cache_discount": 0.9},
     "PRICE LEVER: each repeat costs less (90% off assumed; real discounts, "
     "write fees and expiry differ), but the request is not smaller, so it does "
     "nothing for the context window"),
]

# The levers whose win depends on the baseline you assume. Printed so the
# ranking is never mistaken for a law.
SENSITIVITY = [
    # (agent, what changes, caption, the fix to show or None for the biggest mover, charted)
    ("screen", {"system_prompt_tokens": 4000},
     "Screen agent, if your prompt and tool schemas are 4,000 tokens",
     "Cut the system prompt by 60%", True),
    ("screen", {"prefix_cache_discount": 0.9},
     "Screen agent, if caching is already on",
     "Drop stale screenshots, keep the newest", True),
    ("screen", {"prefix_cache_discount": 0.9},
     "Screen agent, caching on, sliding the window every turn",
     "Keep only the last 5 turns", True),
    ("chat", {"prefix_cache_discount": 0.9, "output_price_multiple": 5.0},
     "Chat agent, caching on and output priced at 5x input", "Halve every agent reply", True),
    ("screen", {"screen_text_tokens": 1000},
     "Screen agent, if the screen's text is 1,000 tokens, not 300",
     "Send the screen's text, not pixels", True),
    ("screen", {"audio_preset": "window-30s"},
     "Screen agent, if your audio model pads every clip to 30 s", None, False),
    ("screen", {"turns": 10}, "Screen agent, if sessions are 10 turns, not 20", None, False),
]


SCREEN_KEYS = ("screenshot_every_n_turns", "image_preset", "drop_old_images",
               "screen_as_text")


def variant(base, changes, label):
    config = copy.deepcopy(base)
    if base["screenshot_every_n_turns"] is None:
        # No screenshots to change, so a screenshot fix cannot apply. Without
        # this, "screenshot every 4th turn" would ADD pictures to a text agent.
        changes = dict((k, v) for k, v in changes.items() if k not in SCREEN_KEYS)
    config.update(changes)
    config["label"] = label
    return config


def overflow_turn(config, limit=400):
    """First turn whose prompt reaches the context window, or None within `limit` turns."""
    _total, rows, _final = simulate(variant(config, {"turns": limit}, "window"))
    for row in rows:
        if row["prompt"] >= CONTEXT_WINDOW:
            return row["turn"]
    return None


OVERRIDES = {}      # set from --turns / --prompt / --cache


def agent_config(name):
    cfg = copy.deepcopy(AGENTS[name][0])
    cfg.update(OVERRIDES)
    return cfg


def rank_levers(base):
    """Run every lever against `base`. Returns (total, scored), best saving first.

    scored rows are (saving, label, new_total, new_final_prompt, costs).
    """
    total = simulate(base)[0]
    scored = []
    for label, changes, costs in LEVERS:
        changed_total, _, changed_final = simulate(variant(base, changes, label))
        scored.append((1.0 - changed_total / float(total), label,
                       changed_total, changed_final, costs))
    scored.sort(key=lambda row: -row[0])
    return total, scored


def design_levers(scored):
    """Design changes that apply to this agent (caching is a billing arrangement)."""
    return [row for row in scored
            if "PRICE LEVER" not in row[4] and abs(row[0]) > 0.0005]


def sensitivity_rows():
    """How far a fix's saving moves when one assumption of an agent changes.

    One row per SENSITIVITY entry: the named fix, or the design fix that moves
    furthest. Used by this script's printout and by the deck's chart.
    """
    def design_savings(cfg):
        base = simulate(cfg)[0]
        out = {}
        for label, changes, costs in LEVERS:
            if "PRICE LEVER" in costs:
                continue
            out[label] = 100.0 * (1.0 - simulate(variant(cfg, changes, label))[0] / float(base))
        return out

    def ranked(savings):
        order = sorted(savings, key=lambda k: -savings[k])
        return dict((label, i + 1) for i, label in enumerate(order))

    rows = []
    for agent, changes, caption, named, charted in SENSITIVITY:
        base_cfg = AGENTS[agent][0]
        before, after_cfg = design_savings(base_cfg), copy.deepcopy(base_cfg)
        after_cfg.update(changes)
        after = design_savings(after_cfg)
        mover = named or max(after, key=lambda k: abs(after[k] - before[k]))
        rows.append({"agent": agent, "caption": caption, "changes": changes,
                     "label": mover, "before": before[mover], "after": after[mover],
                     "rank_before": ranked(before)[mover], "rank_after": ranked(after)[mover],
                     "winner": max(after, key=lambda k: after[k]),
                     "winner_saving": max(after.values()), "charted": charted})
    return rows


def describe(config):
    parts = ["%d turns" % config["turns"],
             "a %s-token system prompt" % tokenbill.human(config["system_prompt_tokens"]),
             "%d-token replies" % config["agent_reply_tokens"]]
    if config["screenshot_every_n_turns"] is not None:
        parts.append("a %dx%d screenshot each turn" % tuple(config["screen_size"]))
    else:
        parts.append("no pictures")
    return ", ".join(parts)


def bill_breakdown(config):
    """Where a session's bill goes, by kind of content.

    An item added on turn t is sent on every turn from t to the end, so its
    cost is its size times the turns remaining. Valid for a plain session (no
    caching, no pruning), which both agents are. Returns (rows, total, sums_ok).
    """
    turns = config["turns"]
    audio_each, image_each = turn_items(config)
    every = config["screenshot_every_n_turns"]
    sends = lambda t: turns - t + 1
    image = 0 if every is None else sum(
        image_each * sends(t) for t in range(1, turns + 1) if (t - 1) % every == 0)
    speech = sum(audio_each * sends(t) for t in range(1, turns + 1))
    reply_tokens = int(round(config["agent_reply_tokens"] * config.get("agent_reply_scale", 1.0)))
    reply = sum(reply_tokens * (sends(t) - 1) for t in range(1, turns + 1))
    prompt = config["system_prompt_tokens"] * config.get("system_prompt_scale", 1.0) * turns
    kind = "Speech" if not config["transcribe_audio"] else "User messages"
    rows = [("Screenshots", image), (kind, speech), ("Agent replies", reply),
            ("System prompt", prompt)]
    total = simulate(config)[0]
    return [(l, v) for l, v in rows if v], total, int(round(sum(v for _, v in rows))) == total


def run_single(name):
    blurb = AGENTS[name][1]
    config = agent_config(name)
    audio_cost, image_cost = turn_items(config)
    total, rows, final_prompt = simulate(config)
    has_screen = config["screenshot_every_n_turns"] is not None

    print()
    print("THE AGENT (%s): %s" % (name, blurb))
    print(textwrap.fill(describe(config), 78))
    print()
    print("Cost of ONE turn's new content:")
    print("  %-8s %7s tokens" % ("speech" if not config["transcribe_audio"] else "message",
                                tokenbill.human(audio_cost)))
    if has_screen:
        print("  %-8s %7s tokens   (%s)"
              % ("screen", tokenbill.human(image_cost), config["image_preset"]))
    print("  %-8s %7s tokens" % ("reply", tokenbill.human(config["agent_reply_tokens"])))
    print()

    print("SESSION, turn by turn")
    print("-" * 78)
    print("%6s %12s %12s %8s" % ("turn", "prompt size", "billed", "images"))
    for row in rows:
        if row["turn"] in (1, 2, 3, 5, 10, 15, config["turns"]):
            print("%6d %12s %12s %8d"
                  % (row["turn"], tokenbill.human(row["prompt"]),
                     tokenbill.human(row["billed"]), row["images"]))
    print("-" * 78)
    print("Total billed prompt tokens for the session: %s" % tokenbill.human(total))
    hit = overflow_turn(config)
    print("Final turn's prompt: %s tokens, %.0f%% of a %s-token window."
          % (tokenbill.human(final_prompt), 100.0 * final_prompt / CONTEXT_WINDOW,
             tokenbill.human(CONTEXT_WINDOW)))
    print(textwrap.fill(
        ("The window fills at turn %d if the session keeps going. Pruning "
         "delays that; caching does not." % hit) if hit else
        "The window is not reached within 400 turns.", 78))
    print()

    parts, _total, ok = bill_breakdown(config)
    if ok:
        print("WHERE THE BILL GOES")
        print("-" * 78)
        for label, value in parts:
            print("%-16s %10s   %5.1f%%" % (label, tokenbill.human(value), 100.0 * value / total))
        print("Sent again: %s of %s tokens (%.1f%%)."
              % (tokenbill.human(total - final_prompt), tokenbill.human(total),
                 100.0 * (total - final_prompt) / total))
        per_session = total / 1e6 * config["price_per_million"]
        print("At $%.2f per million tokens (an assumption): $%.2f per session,"
              % (config["price_per_million"], per_session))
        print("or about $%s a month at %s sessions a day, 30 days."
              % (tokenbill.human(round(per_session * config["sessions_per_day"] * 30)),
                 tokenbill.human(config["sessions_per_day"])))
        print()

    total, scored = rank_levers(config)
    print("ONE FIX AT A TIME, ranked by what it saves on THIS agent")
    print("-" * 78)
    for saving, label, changed_total, _, costs in scored:
        already = ("(already on)" if "PRICE LEVER" in costs and config["prefix_cache_discount"] > 0
                   else "")
        print("%6.1f%%  %-40s %9s tokens %s"
              % (saving * 100.0, label, tokenbill.human(changed_total), already))
        print(textwrap.fill("costs you: " + costs, 78, initial_indent=" " * 9,
                            subsequent_indent=" " * 9))
    print("-" * 78)
    design = design_levers(scored)
    best, worst = design[0], design[-1]
    print("Best design fix:  %.1f%%  %s" % (best[0] * 100.0, best[1]))
    print("Worst design fix: %.1f%%  %s" % (worst[0] * 100.0, worst[1]))
    if config["prefix_cache_discount"] > 0:
        print(textwrap.fill(
            "Caching is already on in this run, so its row shows no saving. It is "
            "a price lever: it makes each repeat cheaper, not the request smaller.", 78))
    else:
        cached_cfg = variant(config, {"prefix_cache_discount": 0.9}, "cached")
        _t, cached_scored = rank_levers(cached_cfg)
        again = [row for row in cached_scored if row[1] == best[1]][0]
        print(textwrap.fill(
            "Caching is listed too, but it is a price lever: it makes each repeat "
            "cheaper, not the request smaller. With caching already on, '%s' saves "
            "%.1f%% instead of %.1f%%." % (best[1], again[0] * 100.0, best[0] * 100.0), 78))
    print()
    mine = [r for r in sensitivity_rows() if r["agent"] == name]
    if OVERRIDES:
        print()
        print(textwrap.fill("Your flags change the assumptions above (%s). The 'ranking is "
                            "not a law' table is for the stock settings: run without flags "
                            "to see it." % ", ".join("%s=%s" % kv for kv in sorted(OVERRIDES.items())), 78))
    elif mine:
        print()
        print("THE RANKING IS NOT A LAW: change one assumption of this agent")
        print("-" * 78)
        for r in mine:
            print(textwrap.fill("%s: '%s' goes from %.1f%% to %.1f%% (rank %d to %d)."
                                % (r["caption"], r["label"], r["before"], r["after"],
                                   r["rank_before"], r["rank_after"]),
                                78, subsequent_indent="  "))
        print("-" * 78)
    print()
    print("Now ask which of these you have actually tuned on your own agent.")
    print()
    print(textwrap.fill("NOTE: %s" % models.provenance_note(), 78))
    print()


def run_both():
    ranked = {}
    for name in ("screen", "chat"):
        total, scored = rank_levers(agent_config(name))
        ranked[name] = (total, scored,
                        dict((row[1], (i + 1, row[0])) for i, row in enumerate(scored)))
    print()
    print("THE SAME TEN FIXES ON TWO AGENTS")
    print("-" * 78)
    for name in ("screen", "chat"):
        print("%-7s %s" % (name, textwrap.fill(
            "%s. Session bill %s tokens." % (describe(agent_config(name)),
                                            tokenbill.human(ranked[name][0])),
            70, subsequent_indent=" " * 8).lstrip()))
    print()
    print("%-38s %15s %15s" % ("fix", "screen agent", "chat agent"))
    print("%-38s %15s %15s" % ("", "saves (rank)", "saves (rank)"))
    print("-" * 78)
    order = [row[1] for row in ranked["screen"][1]]
    for label in order:
        s_rank, s_save = ranked["screen"][2][label]
        c_rank, c_save = ranked["chat"][2][label]
        c_cell = ("%9.1f%% (%2d)" % (c_save * 100.0, c_rank)
                  if abs(c_save) > 0.0005 else "%15s" % "n/a")
        print("%-38s %9.1f%% (%2d) %s" % (label, s_save * 100.0, s_rank, c_cell))
    print("-" * 78)
    screen_design = design_levers(ranked["screen"][1])
    chat_design = design_levers(ranked["chat"][1])
    best_screen, worst_screen = screen_design[0][1], screen_design[-1][1]
    best_chat = chat_design[0][1]
    print("Best design fix on the screen agent: %s" % best_screen)
    print("Best design fix on the chat agent:   %s" % best_chat)
    if best_screen != best_chat:
        rank_c, save_c = ranked["chat"][2][worst_screen]
        print()
        print(textwrap.fill(
            "Different agents, different winners. '%s' came last of the design "
            "fixes on the screen agent and saves %.1f%% on the chat agent "
            "(#%d overall). n/a means the agent has no such item to shrink. "
            "Find out which item dominates YOUR bill before you pick a fix."
            % (worst_screen, save_c * 100.0, rank_c), 78))
    print()


def main():
    which = "screen"
    args = sys.argv[1:]
    if "-h" in args or "--help" in args:
        print(__doc__)
        return
    flags = {"--agent": None, "--turns": int, "--prompt": int, "--cache": float}
    keys = {"--turns": "turns", "--prompt": "system_prompt_tokens",
            "--cache": "prefix_cache_discount"}
    ranges = {"--turns": (2, 400), "--prompt": (0, 1000000), "--cache": (0.0, 0.99)}
    for i, arg in enumerate(args):
        name, _eq, value = arg.partition("=")
        if name in flags:
            if not _eq:
                value = args[i + 1] if i + 1 < len(args) else ""
            try:
                if name == "--agent":
                    which = value
                else:
                    number = flags[name](value)
                    low, high = ranges[name]
                    if not (low <= number <= high):          # also rejects nan
                        raise ValueError
                    OVERRIDES[keys[name]] = number
            except ValueError:
                if name == "--agent":
                    sys.exit("Unknown agent %r." % value)
                low, high = ranges[name]
                sys.exit("%s needs a number from %s to %s, not %r." % (name, low, high, value))
    if which == "both":
        run_both()
    elif which in AGENTS:
        run_single(which)
    else:
        sys.exit("Unknown agent %r. Use --agent screen, chat or both." % which)


if __name__ == "__main__":
    main()
