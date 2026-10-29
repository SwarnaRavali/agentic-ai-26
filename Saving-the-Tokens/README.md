# Saving the Tokens: Efficient Agent Design

Hands-on material for the IEEE AgenticAI Summit 2026 session, Bangalore.
Speaker: Shyamji Tiwari, Applied Scientist, Amazon. Views are my own.

> **Your bill = how big each item is × how many times you send it again.**
> Find the item that dominates your bill, then fix that one.

Small Python scripts that price what images, speech and a whole agent
session cost in tokens. Python 3.7+ only. No install, no API key, no model
download, nothing touches the network.

## Quick start

```bash
git clone https://github.com/ieee-ai/agentic-ai-26.git
cd agentic-ai-26/Saving-the-Tokens
python3 check_setup.py          # expect: PASS. You are ready.
```

On Windows, if `python3` is not found, use `py check_setup.py`. No Python at
all? Open `calc.html` in a browser for the image-cost part.

## Exercises

```bash
python3 ex1_image.py --size 1920x1080   # one screenshot: modelled strategies and real vendor rules
python3 ex2_audio.py                    # what speech costs
python3 ex3_budget.py                   # a 20-turn screen agent, ten fixes ranked
python3 ex3_budget.py --agent both      # the same ten fixes on a chat agent: the ranking flips
```

Do exercise 3's prediction on paper before you run it.

## Take it home

```bash
python3 bill_report.py sample_usage.csv     # then point it at your own log
python3 bill_report.py sample_usage_pruned.csv   # exact "sent again" after pruning (new_tokens)
```

Log the input-token count from each model call into a CSV
(`turn,input_tokens,output_tokens`, plus `new_tokens` if you ever prune) and `bill_report.py` tells you how much of
your bill was content you sent again, and whether your fixed prefix or your
growing conversation dominates.

## What is here

| File | What it does |
|---|---|
| `check_setup.py` | confirms your machine is ready; prints PASS |
| `ex1_image.py` | prices one image under modelled strategies and real vendor rules |
| `ex2_audio.py` | prices speech by duration |
| `ex3_budget.py` | prices a whole session; `--agent screen\|chat\|both` |
| `bill_report.py` | reads your per-call token log |
| `calc.html` | offline image-token calculator |
| `models.py` | every encoder constant, with provenance. **Edit this one.** |
| `tokenbill.py` | the arithmetic (standard library only) |
| `HANDOUT.md` | one-page summary of the talk |
| `slides/` | the deck (`.pptx` and `.pdf`) |

## Read this before quoting a number

The session simulation uses illustrative settings. It is not a measurement of
any shipped model, and 8 of the 10 modelled presets are marked "check" in
`models.py`. The three "real products" rows (Claude standard and
high-resolution, OpenAI tile-based) follow the vendors' published rules as
checked on 2026-10-29, which vendors change between model generations, so
re-check the docs before quoting. The ranking of fixes is a property of the
assumed agent: edit `BASELINE` or `CHAT` in `ex3_budget.py` to match yours.
