"""The Claude bridge (lab/claude_cli.py) as a CrewAI LLM.

CrewAI calls BridgeLLM.call() with the agent's whole transcript. The bridge sends it to lab.llm.structured(),
which runs the Claude CLI with the task's JSON schema (or the script, offline), validates the answer with
pydantic and hands CrewAI the JSON. No model tools: evidence is in the task text, never fetched by the model.
"""
import json

from crewai import BaseLLM

from lab import llm
from patterns import common as c


class BridgeLLM(BaseLLM):
    def __init__(self, agent_id, output_model, script):
        super().__init__(model="claude-cli/bridge", temperature=0)
        self.agent_id, self.output_model, self.script = agent_id, output_model, script

    def call(self, messages, tools=None, callbacks=None, available_functions=None, **kwargs):
        if tools:
            raise RuntimeError("This demo does not allow model tools")
        transcript = messages if isinstance(messages, str) else json.dumps(messages, ensure_ascii=False, default=str)
        c.status(self.agent_id, "active", "thinking…")
        offline = lambda: self.script().model_dump()   # noqa: E731
        answer, tokens = llm.structured(self.agent_id, transcript + "\nReturn only JSON conforming to the supplied "
                                        "schema. Do not use Thought/Action prose.",
                                        self.output_model.model_json_schema(), offline)
        try:
            value = self.output_model.model_validate(answer)
        except ValueError:                 # schema-valid JSON can still break a rule pydantic checks
            value = self.output_model.model_validate(offline())
        c.counted(self.agent_id, tokens)
        return value.model_dump_json()

    def supports_function_calling(self):
        return False

    def supports_stop_words(self):
        return False

    def get_context_window_size(self):
        return 100_000
