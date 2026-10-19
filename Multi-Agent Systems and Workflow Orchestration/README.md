# Multi-Agent Systems and Workflow Orchestration

Workshop by Rahul Verma for IEEE AgenticAI Summit 2026 at IISc Bangalore, 30–31 October 2026.

[Download the presentation](slides/multi-agent-systems-workflow-orchestration.pptx)

## Contents

```text
Multi-Agent Systems and Workflow Orchestration/
├── README.md
├── .gitignore
├── slides/
│   └── multi-agent-systems-workflow-orchestration.pptx
└── demos/
    ├── crewai_lab/          # Visual builder, CrewAI tasks and typed contracts
    ├── marketplace_service/ # Browser evidence, ranking and simulated actions
    ├── n8n_workflows/       # Complete/starter imports and their generator
    ├── runtime/            # n8n and browser dependency manifests
    ├── tests/              # Deterministic action-gate checks
    ├── codex_bridge.py      # Inference through your signed-in Codex CLI
    ├── manage.py
    ├── requirements.txt
    ├── start.sh
    └── stop.sh
```

## Setup

Use Python 3.12, Node.js 24 or later, pnpm, Google Chrome and an installed Codex CLI. The launcher requires macOS or Linux with `lsof`. Each participant signs into their own Codex account.

Run these commands **inside this workshop folder**:

```bash
python3.12 -m venv demos/.venv
demos/.venv/bin/python -m pip install -r demos/requirements.txt
pnpm --dir demos/runtime install --frozen-lockfile
pnpm --dir demos/runtime/browser install
codex login
./demos/start.sh
```

`node` and `codex` must be on PATH. Set `NODE_BIN` and `CODEX_BIN` to executable paths if needed. The Python requirements pin the two direct dependencies; pip resolves their transitive dependencies. A clean install on another operating system has not been verified; native dependencies may need platform build tools.

| Service | URL |
| --- | --- |
| CrewAI lab | <http://127.0.0.1:8765/> |
| n8n editor | <http://127.0.0.1:5678/> |
| Marketplace adapter health | <http://127.0.0.1:8002/health> |
| Simulated action health | <http://127.0.0.1:8001/health> |

On first launch, complete n8n's local owner setup. Import `demos/n8n_workflows/complete-workflow.json` through the n8n editor and publish it. Open <http://127.0.0.1:5678/form/live-browser-codex-shopping> to submit a request. The starter workflow deliberately omits the Browser Agent node for the workshop exercise.

Check status with `demos/.venv/bin/python demos/manage.py status`. Stop with `./demos/stop.sh`.

## CrewAI demo

Use the default request: **Find black running shoes under ₹1,000. Ask me before ordering.**

1. Compare Single agent, Manager → Workers, Peer collaboration and Three-role crew.
2. Change shared versus independent context and optionally add the adversarial reviewer.
3. Edit the role/goal JSON, apply it, and inspect the communication graph and generated Python excerpt. Manager mode uses explicit sequential tasks; graph lines represent task-context links.
4. Run live CrewAI. Fresh public Amazon, Flipkart and Myntra evidence is supplied to every task. Inspect the typed handoffs, unknowns and independent validation.

A recorded replay becomes available after a successful live run and is labeled accordingly. The generated excerpt is not a standalone application. The actual runner lives in `demos/crewai_lab/lab.py`. These agents have no ordering tools.

## n8n demo

The completed workflow follows:

```text
Request → Browser search → Codex ranking → Validate evidence → Route
  ├── No Match
  └── Human Approval → Route decision
       ├── Cancelled
       └── Create Simulated Order → Confirmation
```

Submit the same shopping request through the form. Review the source, observed item price, observation time and unknown fields. Cancel proves the action branch is skipped. Approve simulated order demonstrates the local simulated endpoint, which rechecks proposal identity and evidence freshness. Evidence and approval waits expire after 15 minutes; submit a fresh request when needed.

The result is `SIMULATED`, with `payment_taken: false` and `marketplace_contacted: false`. No real marketplace order or payment occurs. Observed item price is not checkout total; size, stock, delivery, returns and shipping can remain unknown. Marketplace blocking or missing required evidence can produce failure or `NO_MATCH`.

Regenerate workflow exports with `demos/.venv/bin/python demos/n8n_workflows/build_workflows.py`.

## Validation

Run the control checks without contacting marketplaces or invoking the model:

```bash
demos/.venv/bin/python -m unittest discover -s demos/tests -v
```

They check explicit approval, proposal identity, evidence expiry, source host/budget, required colour evidence and unknown proposals. Services bind to `127.0.0.1`. Installed dependencies, credentials, local n8n data, logs and generated run state are ignored.
