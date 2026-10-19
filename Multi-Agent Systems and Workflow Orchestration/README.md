# Multi-Agent Systems and Workflow Orchestration

Hands-on material by Rahul Verma for IEEE AgenticAI Summit 2026 at IISc Bangalore, 30–31 October 2026.

## Slides and screenshots

- [Main presentation — Visual v13](slides/Engineering_Multi_Agent_Systems_Visual_v13.pptx)
- [Expanded presentation — v12](slides/Engineering_Multi_Agent_Systems_Expanded_v12.pptx)
- [Earlier revised presentation](slides/Engineering_Multi_Agent_Systems_Revised.pptx)
- [Workshop companion notes](slides/Workshop_Companion_Notes.md)
- [Eight screenshots: four per demo](demos/screenshots/README.md)

## Two demos

**CrewAI architecture lab:** switch between a single agent, manager/workers, peer collaboration and a three-role crew. Edit roles and goals, compare typed task-context links, inspect generated Python, and run actual CrewAI tasks using your signed-in Codex CLI. Every run collects fresh public marketplace evidence and checks the model output independently.

**n8n orchestration:** a shopping request triggers browser collection, Codex ranking, independent evidence validation, a human approval form and a simulated action. Separate branches handle no match and cancellation. The completed workflow and a deliberately incomplete teaching starter are included.

These demos use public Amazon, Flipkart and Myntra pages. They do not place marketplace orders or take payments. Observed item prices are not checkout totals; stock, size, delivery, returns and shipping can remain unknown. Marketplace blocking can produce an honest failure or no match.

## Setup

Prerequisites: Python 3.12, Node.js 24 or later, pnpm, Google Chrome, and an installed Codex CLI signed in with your own account. This checkout includes source and dependency manifests; installed runtimes, accounts, databases and live proposals are created locally.

Run the commands below **inside this workshop directory**:

```bash
python3.12 -m venv demos/.venv
demos/.venv/bin/python -m pip install -r demos/requirements.reconstruction-lock.txt
pnpm --dir demos/runtime install --frozen-lockfile
pnpm --dir demos/runtime/browser install
codex login
./demos/start.sh
```

The Python requirements snapshot records the tested presenter environment. A first-time install on another operating system has not been verified; native dependency builds may require platform build tools. The launcher requires a POSIX environment with `lsof` (macOS or Linux).

`node` and `codex` must be on PATH. Alternatively set `NODE_BIN` and `CODEX_BIN` to their executable paths before starting. Each participant uses their own login; no authentication file is included.

Open:

- CrewAI lab: <http://127.0.0.1:8765/>
- n8n editor: <http://127.0.0.1:5678/>
- Marketplace adapter health: <http://127.0.0.1:8002/health>
- Simulated action health: <http://127.0.0.1:8001/health>

On first launch, complete n8n's local owner setup. Import `demos/n8n_marketplace/live-browser-codex-hitl-workflow.json` using the n8n editor and publish it. Then open <http://127.0.0.1:5678/form/live-browser-codex-shopping>. The starter JSON omits the browser-search node for the workshop exercise; do not publish it as a complete workflow.

Stop services with `./demos/stop.sh`. Check status with `demos/.venv/bin/python demos/manage.py status`.

## Walkthrough and validation

[Demo instructions](demos/README.md) explain the topology experiments, workflow nodes and approval gate. [Presenter verification](demos/VERIFICATION.md) records earlier live runs; it does not claim that those prices or approval links remain valid. Recorded replay is available after the first successful live CrewAI run on your machine. Screenshot 4 for CrewAI shows a recorded replay; screenshot 4 for n8n shows an earlier successful simulated action.

Run the deterministic control checks without contacting marketplaces or invoking the model:

```bash
demos/.venv/bin/python demos/test_boundaries.py
```

All services bind to `127.0.0.1`. Generated logs, marketplace evidence, proposals and local n8n account data remain ignored inside `demos/`.
