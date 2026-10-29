# Saving the Tokens: one page to take away

IEEE AgenticAI Summit 2026. The scripts you ran are yours. Point them at your
own agent and run them again.

## The whole talk in one line

**Your bill = how big each item is × how many times you send it again.**

Find the item that dominates *your* bill, then pick the fix aimed at it. The
same ten fixes rank in opposite orders on two different agents.

## Three numbers to remember

1. **One 1920×1080 screenshot is 1,222 tokens in the session model (at a
   1,280-token image cap), about 3.1× a 400-token system prompt.** Real
   vendors differ: 1,560 on Claude's standard tier, 2,691 on its
   high-resolution tier, 1,105 on OpenAI's tile-based models.
2. **You send it again every turn.** In a 20-turn screen-agent session,
   90.6% of the bill was content already sent: 31,120 tokens of new
   content, 329,420 billed.
3. **On that agent the system prompt is 2.4% of the bill and screenshots are
   77.9%.** On a text-only chat agent with a 6,000-token prompt it is
   the other way round.

## The same ten fixes on two agents

Screen agent: a voice agent that watches a 1920×1080 screen, 20 turns,
329,420 tokens billed. Chat agent: text only, a 6,000-token system prompt,
400-token replies, 20 turns, 217,000 tokens billed.

Run `python3 ex3_budget.py --agent both` to see them side by side.

| saves | fix | aims at | what it costs you |
|---|---|---|---|
| 81.5% | Turn on prefix caching (90% off) | *not a design change* | a billing arrangement, and it does nothing for the context window |
| 70.5% | Drop stale screenshots, keep the newest | sending it less often | the agent can no longer refer back to what it saw earlier |
| 61.8% | Shrink the image budget 1,280 to 256 | making the item smaller | the screen becomes a 588x336 view; small text is gone |
| 58.8% | Send the screen's text, not pixels | making the item smaller | assumes ~300 tokens of screen text; a big UI tree can cost MORE than the image |
| 56.2% | Keep only the last 5 turns | sending it less often | the agent forgets what it was asked to do |
| 55.6% | Screenshot every 4th turn | sending it less often | the agent is three turns stale when it acts |
| 10.6% | Send a transcript, not the audio | making the item smaller | needs speech recognition; loses tone, emotion and overlap |
| 6.4% | Halve the speech token rate | making the item smaller | coarser audio, so worse recognition of unclear speech |
| 3.5% | Halve every agent reply | making the item smaller | terser answers, capped by how short a useful reply can be |
| 1.5% | Cut the system prompt by 60% | making the item smaller | instructions, examples and guardrails: re-test before you ship it |

(Screen agent shown. On the chat agent, "Cut the system prompt by 60%" saves
33.2% and ranks #2 overall; the screenshot fixes do not apply. Prefix caching
saves 83.5% there.)

## Where the screen agent's bill goes

| | share |
|---|---|
| Screenshots | 77.9% |
| Speech | 12.7% |
| Agent replies | 6.9% |
| System prompt | **2.4%** |

At an ASSUMED $3.00 per million input tokens that session costs about
**$0.99**, or roughly $296,478 a month at 10,000 sessions a day.
Substitute your own price and volume: they are settings in `ex3_budget.py`,
not quoted prices.

## Four things that are easy to get wrong

**A cap can be the whole bill.** On Claude's standard tier a 1080p screenshot
and a 4K screenshot both cost 1,560 tokens, because the image is shrunk to fit
a limit first. A tiled encoder prices the *shape* of your image, not its size.

**Cost is a staircase, and it runs downward too.** Widening an image can make
it cheaper, because a change of shape changes the tile grid.

**A fixed-window audio encoder bills padding.** A 31-second clip costs 3,000
tokens against a 30-second clip's 1,500. Sending the recognised *words*
instead is 33 tokens, 45× cheaper than the padded clip.

**Pruning history and prefix caching fight each other.** With caching on,
"keep only the last 5 turns" does not save 56.2%; it raises the bill by
103.6%, because dropping the oldest items throws away the cached prefix.
Order your context with the volatile parts last.

## The ranking is not a law

It is a property of one baseline. Change one assumption:

- if your audio model pads every clip to 30 s, "send a transcript" goes from
  10.6% to **51.1%**
- if your sessions are 10 turns, "keep only the last 5 turns" goes from
  56.2% to **26.4%**
- if caching is already on, that same fix goes to **-103.6%**
- if your prompt and tool schemas are 4,000 tokens, "cut the system prompt" goes
  from 1.5% to **12.0%**
- on the chat agent, with caching on and output priced at 5× input, "halve
  every reply" goes from 17.5% to **35.9%** and overtakes the prompt fix

## Measure your own agent (30 minutes)

1. Every model response carries token counts (the `usage` field; slide 5).
   Log them for each call into a CSV with a header row:
   `turn,input_tokens,output_tokens`. If you use prompt caching, add
   `cache_read_tokens` and `cache_creation_tokens` too: some providers (Anthropic)
   report `input_tokens` WITHOUT the cached part.
2. Run `python3 bill_report.py your_log.csv`. It prints how much of what you
   paid for was sent again, and whether a big fixed prefix or a growing
   conversation dominates. Try it first on `sample_usage.csv` and
   `sample_usage_chat.csv`, which reproduce this session's two totals. It
   says so plainly when your log cannot support a verdict (history that
   shrinks, caches it cannot see).
3. Pick the fix aimed at what dominates. Then re-run to check the total.

One vendor note: Anthropic's computer-use guidance is to prune old
screenshots in batches rather than every turn, because pruning every turn
changes the cached prefix every turn. This session's model has no cache write
premium, so its "drop stale screenshots, caching on" number (38.1%) is an
upper bound.

For images, send one request without the image and one with, and subtract.
Repeat at four sizes. That is *your* staircase.

The arithmetic here is general. The constants are yours: 8 of the
10 modelled presets in `models.py` are marked "check", and even the
published vendor rules change between model generations. Re-check before you
quote.

## The files

| file | what it does |
|---|---|
| `check_setup.py` | confirms your machine is ready; prints PASS |
| `ex1_image.py` | prices one image under modelled strategies and real vendor rules |
| `ex2_audio.py` | prices speech by duration |
| `ex3_budget.py` | prices a whole session; `--agent screen\|chat\|both` |
| `bill_report.py` | reads YOUR per-call token log and says what dominates |
| `calc.html` | offline image-token calculator, no Python needed |
| `models.py` | every encoder constant, with provenance. **Edit this one.** |
| `tokenbill.py` | the arithmetic. Standard library only. |

Python 3.7+. Nothing to install, nothing to download, nothing touches the
network.
