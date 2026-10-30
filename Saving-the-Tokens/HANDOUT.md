# Saving the Tokens: one page to take away

IEEE AgenticAI Summit 2026. The scripts you ran are yours. Point them at your
own agent and run them again.

[Open the session in Google Colab, nothing to install](https://colab.research.google.com/github/ieee-ai/agentic-ai-26/blob/main/Saving-the-Tokens/Saving_the_Tokens_Colab.ipynb)

## The whole talk in one line

**Your bill = size × sends × price per send.** How big each item is, times how
many times you send it again, times what each send costs.

Shrinking acts on size, pruning on sends, caching on price. Find the item that
dominates *your* bill, then pick the fix aimed at it. The same ten fixes
rank differently on two different agents. Every number below comes from an
EXAMPLE agent with settings you can edit, or from a vendor's published rule;
none is a measurement of a real product's bill.

## Three numbers to remember

1. **Over a 20-turn screen-agent session, screenshots are 75.2% of the bill
   and a 400-token system prompt is 2.3%.** Each screenshot is sent
   again on every later turn; the prompt just repeats. A long prompt can win: in
   this model it overtakes the screenshots at about 12,800 tokens (at 4,000 tokens
   it is 19.4% against 62.1%). One 1920×1080 screenshot is 1,222
   tokens in the model; real vendors differ: 1,560 on Claude's standard tier, 2,691
   on its high-resolution tier, 1,105 on OpenAI's tile-based models.
2. **You send it again every turn.** In a 20-turn screen-agent session,
   90.6% of the input tokens were content already sent: 32,240 tokens of new
   content, 341,180 input tokens in total. That is arithmetic (about 19/21 for 20
   turns, 82.1% at 10, 96.1% at 50), and with 90%-off caching the repeats
   cost about 48.9% of the bill. Input tokens only.
3. **It depends on the agent.** On a text-only chat agent with a 6,000-token
   prompt, the system prompt is the big item (55.3% of its input), and one fix
   swings: cutting the prompt goes from last of the design fixes to first.

## The same ten fixes on two agents

Screen agent: a voice agent that watches a 1920×1080 screen, 20 turns,
341,180 tokens billed. Chat agent: text only, a 6,000-token system prompt,
400-token replies, 20 turns, 217,000 tokens billed.

Run `python3 ex3_budget.py --agent both` to see them side by side.

| saves | fix | aims at | what it costs you |
|---|---|---|---|
| 81.5% | Turn on prefix caching (90% off) | *the price of each send* | each repeat costs less (90% off assumed; real discounts, write fees and expiry differ), but the request is not smaller, so it does nothing for the context window |
| 68.1% | Drop stale screenshots, keep the newest | sending it less often | the agent cannot look back; 2 to 3 images are safer for an agent that acts, and dropping one every turn breaks a cache (vendors advise batches) |
| 59.7% | Shrink the image budget 1,280 to 256 | making the item smaller | the screen becomes a 588x336 view: small text and click targets are unreadable, so the saving is bought with capability |
| 56.8% | Send the screen's text, not pixels | making the item smaller | assumes ~300 tokens of screen text: it saves nothing at 1,222 and costs more above that; useless for canvases and charts |
| 56.2% | Keep only the last 5 turns | sending it less often | the agent forgets the task unless you pin it; summarising instead costs a call not priced here; sliding every turn breaks a cache |
| 53.7% | Screenshot every 4th turn | sending it less often | the agent acts on a screen up to three turns old |
| 13.7% | Send a transcript, not the audio | making the item smaller | needs speech recognition, whose cost, delay and errors are not priced here; loses tone and overlap |
| 7.9% | Halve the speech token rate | making the item smaller | not a knob an API gives you: it is a property of the audio encoder |
| 3.3% | Halve every agent reply | making the item smaller | terser answers; output tokens, usually priced higher, are not counted here |
| 1.4% | Cut the system prompt by 60% | making the item smaller | instructions, examples and guardrails: re-test before you ship it |

(Screen agent shown, uncached. Ranked by tokens saved, not by what survives your
task. On the chat agent, "Cut the system prompt by 60%" saves 33.2% and ranks
first among the design fixes (second counting caching); the six screenshot and audio fixes do not apply. Caching is a
price lever: it makes each repeat cheaper but the request is no smaller. Its
81.5% assumes a 90% discount; at 50% it is about 45%.)

## Where the screen agent's bill goes

| | share |
|---|---|
| Screenshots | 75.2% |
| Speech | 15.8% |
| Agent replies | 6.7% |
| System prompt | **2.3%** |

At an ASSUMED $3.00 per million input tokens that session costs about
**$1.02**, or roughly $307,062 a month at 10,000 sessions a day for 30 days.
Substitute your own price and volume: they are settings in `ex3_budget.py`,
not quoted prices, and the traffic is made up.

## Five things that are easy to get wrong

**A cap can be the whole bill.** On Claude's standard tier a 1080p screenshot
and a 4K screenshot both cost 1,560 tokens, because the image is shrunk to fit
a limit first. A tiled encoder prices the *shape* of your image, not its size.

**Resending also fills the context window.** The request grows every turn
until it hits the model's context window (here 128,000 tokens, at turn 80).
Caching does not move that; pruning does. `max_tokens` is different: it only
caps the length of one reply.

**A fixed-window audio encoder pads.** A Whisper-style encoder works in 30-second
windows: 1,500 positions for 30 seconds, 3,000 for 31. Whether a product bills
that, look for a step at 30 seconds in your own usage numbers. The words as
text are 33 tokens against 256 for 8 seconds of speech at Gemini's published 32 a second
(8× fewer), before the cost of recognising them.

**Pruning history and prefix caching fight each other.** With caching on,
sliding a "keep only the last 5 turns" window every turn does not save
56.2%; it raises the bill by 103.7%, because every turn changes the start of
the prompt and the cache is lost. Both together cost 128,630 tokens, against
63,133 for caching alone and 149,420 for pruning alone. Prune in batches, and
order your context with the volatile parts last.

## The ranking is not a law

It is a property of one baseline. Change one assumption:

- if your audio model pads every clip to 30 s, "send a transcript" goes from
  13.7% to **51.1%**
- if caching is already on, "drop stale screenshots" falls from 68.1% to **36.8%**
  and shrinking the image becomes the best fix
- if the screen's text is 1,000 tokens, not 300, "send the screen's text" falls to about 14%
- if your sessions are 10 turns, "keep only the last 5 turns" goes from
  56.2% to **26.4%**
- if caching is already on, that same fix goes to **-103.7%**
- if your prompt and tool schemas are 4,000 tokens, "cut the system prompt" goes
  from 1.4% to **11.6%**
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
   `sample_usage_chat.csv`, which reproduce this session's two totals (they are
   generated by the simulator, so they check the arithmetic, not the world). It
   says so plainly when your log cannot support a verdict (history that
   shrinks, caches it cannot see).
3. Pick the fix aimed at what dominates. Then re-run to check the total.

One vendor note: Anthropic's computer-use guidance is to prune old
screenshots in batches rather than every turn, because pruning every turn
changes the cached prefix every turn, and for its newest models to avoid pruning on
the client and use the server-side option instead. Check the docs for your model.
This session's model has no cache write premium and prunes every turn, so its
"drop stale screenshots, caching on" number (36.8%) is an upper bound.

For images, send one request without the image and one with, and subtract.
Repeat at four sizes. That is *your* staircase.

The arithmetic here is general. The constants are yours: 7 of the
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
| `Saving_the_Tokens_Colab.ipynb` | the whole session as a Colab notebook, nothing to install |
| `calc.html` | offline image-token calculator, no Python needed |
| `models.py` | every encoder constant, with provenance. **Edit this one.** |
| `tokenbill.py` | the arithmetic. Standard library only. |

Python 3.7+. Nothing to install, nothing to download, nothing touches the
network.
