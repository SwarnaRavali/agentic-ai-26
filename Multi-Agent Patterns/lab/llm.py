"""Every model call in the repo goes through here.

ask(agent, role, context, actions)   one decision: {"action": <one of actions>, "say": <short text>}
structured(agent, prompt, schema)    any JSON schema; used by the CrewAI bridge (crews/llm.py)
configure(mode, model)               switch the model for the next run (the pages do this per run)
last()                               this thread's last call: model, duration, live or scripted

LAB_LLM=offline   (default) scripted replies. Same result every run. Use this on stage.
LAB_LLM=openai    any OpenAI-compatible server: OpenAI, Groq, vLLM, Ollama, LM Studio.
                  Set OPENAI_API_KEY, LAB_MODEL, and OPENAI_BASE_URL if not OpenAI.
LAB_LLM=anthropic Set ANTHROPIC_API_KEY and LAB_MODEL.
LAB_LLM=claude    the local Claude Code CLI with your saved login, no API key (lab/claude_cli.py).
                  LAB_MODEL is optional: sonnet (default), haiku or opus. About 5-15 s per call.

Real models are not deterministic. The guardrails are written in code, so they hold
whatever the model says. That is the point of the lab.

On stage a real model can be slow or fail. Each call has a timeout (LAB_TIMEOUT, seconds),
and if a call fails, the agents fall back to their scripted replies for the rest of the run,
and say so. The run carries on.
"""
import json
import os
import re
import threading
import time

from lab import trace

MODES = ("offline", "openai", "anthropic", "claude")
BRAINS = {"offline": ("offline", ""), "claude-haiku": ("claude", "haiku"), "claude-sonnet": ("claude", "sonnet")}   # the pages' picker
MODE = MODEL = ""
TIMEOUT = 20.0
_meta = threading.local()   # the scouts call the model from parallel threads


def configure(mode, model=""):
    """Choose the model for the next run. Raises ValueError on a bad combination."""
    global MODE, MODEL, TIMEOUT, _client
    mode = (mode or "offline").lower()
    if mode not in MODES:
        raise ValueError(f"LAB_LLM={mode!r}: use offline, openai, anthropic or claude (see .env.example).")
    if mode in ("openai", "anthropic") and not model:
        raise ValueError(f"LAB_LLM={mode} needs LAB_MODEL set to a model name (see .env.example).")
    MODE, MODEL, _client = mode, model or "", None
    TIMEOUT = float(os.getenv("LAB_TIMEOUT") or ("90" if mode == "claude" else "20"))
    reset()


def last():
    return getattr(_meta, "value", {"live": False})


def _note(meta):
    _meta.value = meta


def ask(agent, role, context, actions, offline=None, fields=None):
    """offline: the scripted reply for this call (default: the shopping team's script).
    fields:  extra reply fields the model must fill, as {name: description}. The caller checks them."""
    script = (lambda: dict(offline)) if offline else (lambda: _offline(agent, context))
    _note({"live": False, "model": "scripted"})
    if MODE == "offline":
        reply = script()
        tokens = _estimate(role, context, reply)
    elif _down:
        reply, tokens = _fallback(script, role, context, f"model unavailable ({_down})")
    else:
        try:
            reply, tokens = _real(role, context, actions, fields)
        except Exception as e:   # timeout, rate limit, bad key, network: keep the demo going
            _trip(e)
            reply, tokens = _fallback(script, role, context, f"model error: {type(e).__name__}")
            trace.event("llm_error", agent=agent, error=f"{type(e).__name__}: {e}"[:300])
    if reply.get("action") not in actions:
        bad = reply.get("action")
        if offline:
            reply = {**script(), "say": f"(model gave action {bad!r}, using the script) {script()['say']}"}
        else:
            reply = {"action": actions[0], "say": f"(model gave action {bad!r}, using {actions[0]!r}) {reply.get('say', '')}"}
    trace.event("llm", agent=agent, mode=MODE, role=role, context=context, reply=reply, tokens=tokens, meta=last())
    return reply, tokens


# Circuit breaker: after the first failed call, the rest of the run uses scripted replies at once,
# instead of every agent waiting out its own timeout. reset() closes it again (each new run).
_down = None


def _trip(error):
    global _down
    _down = type(error).__name__


def reset():
    global _down
    _down = None


def structured(agent, prompt, schema, offline):
    """One call that must return JSON matching `schema`. offline() gives the scripted answer.
    Returns (answer, tokens). Falls back to the script on any model failure, like ask()."""
    _note({"live": False, "model": "scripted"})
    answer = None
    if MODE != "offline" and not _down:
        try:
            if MODE == "claude":
                from lab import claude_cli
                answer, tokens, meta = claude_cli.infer(prompt, schema, MODEL, TIMEOUT)
                _note(meta)
            else:
                answer, tokens = _real_text(prompt + "\n\nReply with ONLY a JSON object matching this schema: "
                                            + json.dumps(schema))
        except Exception as e:
            _trip(e)
            trace.event("llm_error", agent=agent, error=f"{type(e).__name__}: {e}"[:300])
    if answer is None:
        answer = offline()
        tokens = 220 + (len(prompt) + len(json.dumps(answer, ensure_ascii=False))) // 4
        if MODE != "offline":
            _note({"live": False, "model": f"scripted (model unavailable: {_down})"})
    trace.event("llm", agent=agent, mode=MODE, prompt=prompt[-4000:], reply=answer, tokens=tokens, meta=last())
    return answer, tokens


def _fallback(script, role, context, why):
    reply = script()
    reply = {**reply, "say": f"({why}; scripted reply) {reply['say']}"}
    return reply, _estimate(role, context, reply)


# ---------------------------------------------------------------- offline script

def _offline(agent, ctx):
    ev = ctx.get("event", {})
    name, price = ev.get("name", "item"), ev.get("price")

    if agent == "watcher":
        return {"action": "trigger",
                "say": f"{name} dropped ₹{ev.get('old_price')} → ₹{price}. Matches the saved goal. Waking the team."}

    if agent == "scout":
        item = ctx["item"]
        if item["price"] <= ctx["goal"]["max_price"]:
            return {"action": "offer", "say": f"{ctx['store']}: {item['name']} at ₹{item['price']}. Under budget."}
        return {"action": "no_offer", "say": f"{ctx['store']}: {item['name']} at ₹{item['price']}. Over budget."}

    if agent == "evaluator":
        ok = [o for o in ctx["offers"] if o["price"] <= ev["goal"]["max_price"]]
        if not ok:
            return {"action": "reject", "say": f"None of {len(ctx['offers'])} offers is under budget."}
        best = min(ok, key=lambda o: o["price"])
        return {"action": "recommend", "say": f"{len(ctx['offers'])} offers in. Best: {best['name']} at "
                                              f"₹{best['price']} ({best['store']})."}

    # deal / budget agents
    turn = ctx.get("turn", 0)
    other = ctx.get("other_last") or {}
    owner = ctx.get("owner")

    if ctx.get("owner_rule"):
        if owner and owner != agent:
            return {"action": "stand_down", "say": f"{owner.title()} agent owns this task. Standing down."}
        if owner == agent:
            if ctx.get("chaos") and agent == "deal":
                return {"action": "recheck", "say": "Price might drop further. Re-checking all stores…"}
            return {"action": "buy", "say": f"I own this task. Buying {name} at ₹{price}."}
        return {"action": "claim", "say": "Claiming the purchase task."}

    # No ownership rule: both agents think the purchase is theirs.
    if not other:
        return {"action": "claim", "say": "Good deal. I'll handle this purchase."}
    if not ctx.get("i_added") and turn >= 3:
        return {"action": "add_to_cart", "say": "Adding to cart now before the price goes back up."}
    lines = ["No, purchases are my job.", "You're wrong, I own this.", "Re-planning… still mine.",
             "I was assigned purchases.", "Please stand down."]
    return {"action": "dispute", "say": lines[turn % len(lines)]}


def _estimate(role, ctx, reply):
    # Rough token count: prompt + context + reply, about 4 characters per token.
    text = role + json.dumps(ctx, ensure_ascii=False) + json.dumps(reply, ensure_ascii=False)
    return 220 + len(text) // 4


# ---------------------------------------------------------------- real models

_client = None
_client_lock = threading.Lock()   # the scouts call the model from parallel threads


def _get_client():
    global _client
    with _client_lock:
        if _client is None:
            if MODE == "anthropic":
                import anthropic
                _client = anthropic.Anthropic(timeout=TIMEOUT, max_retries=1)
            else:
                from openai import OpenAI
                _client = OpenAI(base_url=os.getenv("OPENAI_BASE_URL") or None, timeout=TIMEOUT, max_retries=1)
        return _client


def _prompt(role, context, actions, fields=None):
    extra = "".join(f", \"{k}\": {v}" for k, v in (fields or {}).items())
    return (
        f"{role}\n\nCurrent situation (JSON):\n{json.dumps(context, ensure_ascii=False)}\n\n"
        f"Reply with ONLY a JSON object: {{\"action\": one of {actions}, \"say\": \"one short sentence\"{extra}}}"
    )


def _schema(actions, fields):
    props = {"action": {"type": "string", "enum": list(actions)}, "say": {"type": "string"}}
    for k in fields or {}:
        props[k] = {"type": "array", "items": {"type": "string"}}
    return {"type": "object", "properties": props}


def _parse(text):
    match = re.search(r"\{.*\}", text, re.S)
    try:
        return json.loads(match.group(0)) if match else {"say": text}
    except json.JSONDecodeError:
        return {"say": text}


def _real(role, context, actions, fields=None):
    prompt = _prompt(role, context, actions, fields)
    if MODE == "claude":
        from lab import claude_cli
        reply, tokens, meta = claude_cli.infer(prompt, _schema(actions, fields), MODEL, TIMEOUT)
        _note(meta)
        return reply, tokens
    reply, tokens = _real_text(prompt)
    return reply, tokens


def _real_text(prompt):
    start = time.time()
    client = _get_client()
    if MODE == "anthropic":
        res = client.messages.create(model=MODEL, max_tokens=400, messages=[{"role": "user", "content": prompt}])
        text = "".join(b.text for b in res.content if getattr(b, "type", "") == "text")
        tokens = res.usage.input_tokens + res.usage.output_tokens
    else:
        res = client.chat.completions.create(model=MODEL, max_tokens=400, temperature=0.2,
                                             messages=[{"role": "user", "content": prompt}])
        text = res.choices[0].message.content or ""
        tokens = res.usage.total_tokens if res.usage else len(prompt) // 4
    _note({"provider": MODE, "model": MODEL, "duration_ms": round((time.time() - start) * 1000), "live": True})
    return _parse(text), tokens


try:
    configure(os.getenv("LAB_LLM", "offline"), os.getenv("LAB_MODEL", ""))
except ValueError as e:
    raise SystemExit(str(e))
