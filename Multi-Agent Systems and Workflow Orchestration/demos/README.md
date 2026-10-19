# Live multi-agent workshop demos

This is a reconstruction from Md1.md, Md2.md and the supplied photos, not the original hashed workshop source.

Both demos use your own installed, signed-in **Codex CLI** as the LLM. Set `CODEX_BIN` if it is not on PATH. Both collect fresh public Amazon, Flipkart and Myntra evidence with Playwright and system Chrome. No provider API key is required. Neither demo buys anything.

Install dependencies using the setup instructions in [the workshop README](../README.md) first. Import and publish the completed workflow in your local n8n; account setup and workflow state are not included. Recorded replay becomes available after your first successful live CrewAI run.

## Open the demos

- CrewAI visual builder: http://127.0.0.1:8765/
- n8n editor: http://127.0.0.1:5678/
- Completed workflow: http://127.0.0.1:5678/workflow/IISCLiveBrowserCodex
- Live request form: http://127.0.0.1:5678/form/live-browser-codex-shopping

On the first n8n launch, complete the local owner setup yourself. This account is separate from the existing Codex login. Do not paste credentials into the chat.

## Start and stop

From this workshop folder:

```bash
./demos/start.sh
./demos/stop.sh
```

The launcher uses the workspace `.venv`, project-local n8n package, and Node.js on PATH (or `NODE_BIN`). It binds services to 127.0.0.1 and keeps logs in `demos/logs/`. The stop script stops only processes recorded by this launcher whose commands belong to this directory.

Ports:

| Port | Service |
|---|---|
| 8765 | CrewAI architecture builder and live-run API |
| 8002 | Browser search and Codex ranking adapter |
| 8001 | Simulated action endpoint |
| 5678 | n8n editor and forms |

## CrewAI demo sequence

1. Open the builder and leave the default request: **Find black running shoes under ₹1,000. Ask me before ordering.**
2. Select Single agent. Inspect its one task and zero task-context edges.
3. Select Manager → Workers. Compare shared typed context with independent workers. Add the adversarial reviewer if useful.
4. Edit the JSON role/goal definitions and click **Apply and generate code**. The delivery-specialist challenge button intentionally weakens that role's goal; deterministic checks retain authority.
5. Select Peer collaboration and compare shared versus isolated context. Three-role crew shows Request Analyst, Offer Evaluator and Policy Reviewer.
6. Choose **Run live CrewAI**. Each run opens fresh public search pages and inspects up to two in-budget product pages per source. It then invokes Codex for the actual CrewAI tasks.
7. Inspect browser evidence, each typed handoff, and independent validation. `NO_MATCH` is valid when the required category/colour or budget cannot be established. A validation failure blocks action and stays visible.

The ₹4,000 scenarios are explicit constraint experiments. Required size and delivery promises are often unverified by public search pages, so those experiments can stop with NO_MATCH. No fixed winner is promised.

Generated code is a topology excerpt, not a self-contained application. `crewai_hands_on/lab.py` contains the full live runner, Codex BaseLLM adapter and independent checks. The builder's graph shows **task context edges**; every task also receives the freshly collected browser evidence.

Saved-run replay reads real earlier outputs and is labeled **RECORDED REPLAY**. It does not invoke the model or represent current prices. Earlier fixture-based test runs are not live marketplace runs.

## n8n demo sequence

Import and publish the completed workflow on your machine. Its eleven nodes are:

```text
Shopping Request
  Browser Agent — Search Marketplaces
  Codex Agent — Normalize & Rank
  Validate Live Evidence
  Route Recommendation
    No Match
    Human Approval
      Route Human Decision
        Cancelled
        Create Simulated Order
          Order Confirmation
```

1. Open the live request form and submit the default ₹1,000 request.
2. The Browser Agent calls `POST http://127.0.0.1:8002/search`.
3. The Codex Agent calls `POST http://127.0.0.1:8002/recommend-live` with the collected evidence.
4. Independent adapter and n8n checks verify the selected candidate, source host, observed item price, budget and timestamp. Model claims are not used to manufacture evidence.
5. Eligible observations reach a durable approval form. Missing or invalid required evidence reaches No Match.
6. Inspect the real source link, item price, observation time, provenance and unknown fields.
7. Choose Cancel to prove the simulated-action endpoint is unreachable from that branch. For an explicit simulated test, choose Approve simulated order.
8. The local action service checks the exact persisted proposal identity and its freshness again. Evidence expires after 15 minutes. It uses an idempotent record per proposal and returns `SIMULATED`, `payment_taken: false`, and `marketplace_contacted: false`.

The approval wait is limited to 15 minutes; a missing or timed-out decision falls through to cancellation. Adapter errors and invalid evidence stop without action. The action service stores proposals locally so an n8n wait can survive an adapter restart. If evidence expires or changes, submit a new request and approve the refreshed proposal.

The STARTER workflow deliberately omits Browser Agent. Add an HTTP Request node and connect Shopping Request → Browser Agent → Codex Agent, using the mappings visible in the completed workflow. Do not publish the incomplete starter as a finished workflow.

## Evidence boundaries

- Observed **item price** is not a verified **checkout total**. Shipping, stock, size, delivery and return policies remain explicit unknowns unless separately evidenced.
- The demo approves only a simulated action. A real purchase needs additional checks and a separate commerce integration, which this project does not contain.
- Product colour/category must be supported by the supplied page evidence. A search query or URL slug alone is insufficient.
- The browser records source failures. If all sites fail or block automation, it returns an honest failure or NO_MATCH; it does not silently substitute fixtures.
- Public search-index fallback is explicitly labeled and never presented as a direct retailer-page observation.
- The parser is deliberately bounded to black running shoes with a numeric budget and optional explicit UK size/delivery deadline. It is not a general shopping agent.

## Runtime and files

Installed for this reconstruction:

- Python 3.12, project `.venv`
- CrewAI 1.15.28, Pydantic 2.12.5
- n8n 2.43.7, project-local package and pnpm lockfile
- Existing Codex CLI 0.163.0-alpha.10.2, existing ChatGPT login
- Playwright 1.62.1 and system Google Chrome

The original CLI version is not installed over the current app. Each inference uses read-only, ephemeral `codex exec`, structured output, disabled shell/web search, and the account-default model. No authentication file is copied into the project. Provider API keys are removed from child inference environments.

Important files:

- `codex_bridge.py`: structured Codex inference and tool-activity rejection
- `crewai_hands_on/lab.py`: topology construction, CrewAI adapter, typed contracts, validation
- `crewai_hands_on/server.py`: builder API and background live runs
- `crewai_hands_on/builder.html`: editable lab UI
- `marketplace_service/browser_search.cjs`: actual public-page collection
- `marketplace_service/service.py`: search, ranking, persisted proposals, simulated action
- `n8n_marketplace/build_workflows.py`: portable workflow generator
- `n8n_marketplace/live-browser-codex-hitl-workflow.json`: completed workflow
- `n8n_marketplace/live-browser-codex-hitl-starter.json`: teaching starter
- `runs/`: actual live evidence and recorded outputs, not current price guarantees
- `.n8n-live/`: local n8n account/database; do not distribute or publish
- `test_boundaries.py`: regression checks for the action gate

Regenerate JSON with `demos/.venv/bin/python demos/n8n_marketplace/build_workflows.py`. Import/publish through n8n while preserving the local owner database. Restart n8n after CLI publish operations.

Run control checks with `demos/.venv/bin/python demos/test_boundaries.py`.

## Documentation used

- [Codex noninteractive execution](https://learn.chatgpt.com/docs/non-interactive-mode)
- [CrewAI custom LLMs](https://docs.crewai.com/en/learn/custom-llm)
- [n8n CLI](https://docs.n8n.io/deploy/host-n8n/configure-n8n/use-the-command-line.md)

## Verification performed

See `VERIFICATION.md` for the completed live CrewAI runs, n8n browser tests, regression checks and the remaining CrewAI browser-permission limitation. Actual screenshots are in `runs/n8n-*.png`.
