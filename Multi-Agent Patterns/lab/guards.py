"""The three guardrails. Each is a few lines of code, and each can be switched off to show what it prevents.

They are read from the run's config, not baked into the graph, so a rewind can replay
the same moment with different guardrails (python run.py --rewind N).
"""
from langgraph.types import interrupt

MAX_TURNS = 6
MAX_TOKENS = 5_000


def enabled(config, name):
    return config["configurable"].get("guards", {}).get(name, True)


# Guardrail 1 · one owner per task. First claim wins; code rejects any other claim.
# Anthropic's research agents duplicated each other's work until each one owned a clear task.
def claim(state, name):
    owner = state.get("owner")
    return name if owner in (None, name) else None


# Guardrail 2 · budget and stop. Checked before every hop; when it runs out, escalate to a human.
# In 2025 a team reported a ~$47,000 bill after two agents looped for 11 days with no cap.
def within_budget(state):
    return state.get("turn", 0) < MAX_TURNS and state.get("tokens", 0) < MAX_TOKENS


# Guardrail 3 · human approval. Pauses the graph and saves its state; resumes with the human's answer.
# In 2025 Replit's coding agent deleted a production database during a code freeze.
def approve(proposal):
    return interrupt(proposal) == "approve"
