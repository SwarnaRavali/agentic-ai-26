"""Refresh the code excerpts in web/talk.html (sections 2 and 3) from the repo's real source.

  python web/build_code.py

Run it after you change code in patterns/, crews/ or lab/: each tour step names a function, a class or a
start/end marker, and the excerpt (with its true line numbers) is copied into the page between
/*CODE*/ and /*END*/. Lines matching the step's pattern are highlighted.
"""
import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "web" / "talk.html"

# step id: ([(file, what), ...], highlight regex)
# what: a list of top-level names, or ("from", start marker, end marker[, extra lines]) for a slice
STEPS = {
    "lg_state": ([("patterns/l2_team.py", ["State"])], r"Annotated"),
    "lg_node": ([("patterns/l2_team.py", ["evaluator"])], r"return \{|c\.think\(|rejected"),
    "lg_edges": ([("patterns/l0_pipeline.py", ["build"])], r"add_edge|add_node|compile"),
    "lg_route": ([("patterns/l1_orchestrator.py", ["route"]), ("patterns/l1_orchestrator.py", ["build"])],
                 r"def route|add_conditional_edges|add_edge\(\"worker\", \"planner\"\)"),
    "lg_send": ([("patterns/l2_team.py", ["fan_out", "scout"])], r"Send\(|def scout\(inp\)|return \{\"offers\""),
    "lg_cycle": ([("patterns/l2_team.py", ["after_critic", "after_evaluator"]),
                  ("patterns/l2_team.py", ["build"])], r"add_conditional_edges|return \"evaluator\"|return \"critic\""),
    "lg_critic": ([("patterns/l2_team.py", ["critic"])], r"seller_check|flagged =|\"rejected\""),
    "lg_hitl": ([("lab/guards.py", ["approve"]), ("lab/runner.py", ["_drive"])], r"interrupt|Command\(resume"),
    "lg_event": ([("patterns/l3_event.py", ["run"])], r"wait_for_drop|invoke\("),
    "lg_llm": ([("patterns/common.py", ["think"]), ("lab/claude_cli.py", ["infer"])],
               r"llm\.ask|--json-schema|structured_output|permission_denials"),
    "cr_agent": ([("crews/kit.py", ["agent"])], r"Agent\("),
    "cr_task": ([("crews/kit.py", ["task"]), ("crews/contracts.py", ["Shortlist", "Choice"])], r"Task\(|output_pydantic"),
    "cr_seq": ([("crews/l0_sequential.py", ["build"])], r"Process\.sequential|context=\["),
    "cr_ctx": ([("crews/l1_planned.py", ("from", "    plan = kit.task(", "                verbose=False)"))], r"context="),
    "cr_async": ([("crews/l2_guardrail.py", ("from", "    scouts, tasks = [], []", "    return Crew("))],
                 r"async_execution|context=list"),
    "cr_guard": ([("crews/l2_guardrail.py", ("from", "    def critic(output):", "Verified seller. Approved.", 1)),
                  ("crews/l2_guardrail.py", ("from", "    evaluator = kit.agent(", "guardrail_max_retries=2))"))],
                 r"return False|return True|guardrail"),
    "cr_flow": ([("crews/l3_flow.py", ["PriceWatch"])], r"@start|@router|@listen|return \"trigger\""),
    "cr_llm": ([("crews/llm.py", ["BridgeLLM"])], r"def call|structured\(|model_validate|BaseLLM"),
}

# Not in this repo (the bridge has no tool calling): the standard shape, shown as-is.
STATIC = {
    "cr_hier": {"file": "CrewAI · not used in this repo", "note": "standard shape", "code": '''from crewai import Agent, Crew, Process, Task

search = Agent(role="Search", goal="Find matching listings", backstory="…")
size = Agent(role="Size", goal="Check the size is in stock", backstory="…")
seller = Agent(role="Seller check", goal="Verify the seller", backstory="…")

crew = Crew(
    agents=[search, size, seller],
    tasks=[Task(description="Buy black running shoes, size 9, under ₹1,000",
                expected_output="One verified listing")],
    process=Process.hierarchical,     # a manager plans and delegates at run time
    manager_llm="claude-sonnet-...",  # needs a model with tool calling
)
result = crew.kickoff()''', "hl": [10, 11]},
}


def excerpt(file, what):
    lines = (ROOT / file).read_text(encoding="utf-8").splitlines()
    if isinstance(what, tuple):                    # ("from", start marker, end marker[, extra lines])
        a, b, extra = what[1], what[2], (what[3] if len(what) > 3 else 0)
        i = next(n for n, line in enumerate(lines) if line.startswith(a))
        j = next(n for n in range(i, len(lines)) if b in lines[n]) + extra
        return i + 1, lines[i:j + 1]
    tree = ast.parse("\n".join(lines))
    spans = []
    for node in tree.body:
        if getattr(node, "name", None) in what:
            start = min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])])
            spans.append((start, node.end_lineno))
    if len(spans) != len(what):
        raise SystemExit(f"{file}: could not find all of {what}")
    a, b = min(s for s, _ in spans), max(e for _, e in spans)
    return a, lines[a - 1:b]


def build():
    code = {}
    for sid, (parts, hl) in STEPS.items():
        out, nums = [], []
        for k, (file, what) in enumerate(parts):
            start, lines = excerpt(file, what)
            if len(parts) > 1 and (k == 0 or file != parts[k - 1][0]):
                out.append(f"# {file}")
                nums.append("")
            elif k:
                out.append("…")
                nums.append("")
            out += lines
            nums += [start + n for n in range(len(lines))]
        files = sorted({f for f, _ in parts})
        code[sid] = {"file": " · ".join(files), "code": "\n".join(out), "nums": nums,
                     "hl": [n for n, line in enumerate(out) if re.search(hl, line)],
                     "note": None if len(parts) == 1 else f"{len(parts)} excerpts"}
    for sid, c in STATIC.items():
        code[sid] = {**c, "nums": [n + 1 for n in range(c["code"].count("\n") + 1)]}
    return code


def main():
    page = PAGE.read_text(encoding="utf-8")
    data = json.dumps(build(), ensure_ascii=False)
    new, n = re.subn(r"/\*CODE\*/.*?/\*END\*/", lambda m: "/*CODE*/" + data + "/*END*/", page, flags=re.S)
    if n != 1:
        raise SystemExit("talk.html: the /*CODE*/ … /*END*/ marker was not found")
    PAGE.write_text(new, encoding="utf-8")
    print(f"talk.html: {len(STEPS) + len(STATIC)} excerpts refreshed")


if __name__ == "__main__":
    main()
