# Engineering Multi-Agent Systems — companion notes

## Delivery plan

Allow 40 minutes for slides and demos and 5 minutes for questions or recovery. Introduce the shopping request in the CrewAI section. The main deck is `Engineering_Multi_Agent_Systems_Visual_v13.pptx`; v12 and the earlier revised deck are included as alternatives.

The opening story: a single loop couples interpretation, investigation, evaluation and tool authority; specialist roles expose handoffs; schemas expose structure; deterministic checks and permissions enforce policy; workflows preserve state and control action. Multiple agents add latency, cost and failure modes, so evaluate the benefit before adding them.

## One running request

> Find black running shoes under ₹1,000. Ask me before ordering.

Keep this budget in both demos. Observed item price is not checkout total. Size, stock, delivery, returns and shipping remain explicit unknowns unless independently evidenced. Missing required evidence must block a hard requirement; NO_MATCH is a valid result.

## CrewAI walkthrough

Follow [setup](../README.md) and open <http://127.0.0.1:8765/>.

1. Start with Single agent and its one task with no context edges.
2. Switch to Manager → Workers. Explain the coordinator, specialists and synthesis task. These are explicit sequential tasks, not hidden delegation.
3. Switch to Peer collaboration. Compare shared typed context with independent peers. Every task receives the same fresh browser evidence; graph edges represent additional task context.
4. Edit role/goal JSON, apply it and inspect the generated Python excerpt.
5. Run live CrewAI. Inspect source evidence, typed model outputs and independent validation. The agents have no order tools.

Replay becomes available after a successful live run. It must remain labeled RECORDED REPLAY; it does not invoke the model again or establish current prices.

## n8n walkthrough

Open <http://127.0.0.1:5678/>. Complete local owner setup, import the completed JSON workflow and publish it. Use the incomplete starter only for the exercise of adding the Browser Agent node.

Open <http://127.0.0.1:5678/form/live-browser-codex-shopping> and submit the same request. Walk through browser collection, Codex ranking, deterministic validation and routing. If eligible evidence exists, review the human approval form. It exposes the source, observation time, observed item price and unknowns.

Cancel proves that no simulated action runs on that branch. For an explicit simulated demonstration, Approve simulated order reaches the local action service, which rechecks proposal identity and evidence freshness. Its output is SIMULATED, payment_taken=false and marketplace_contacted=false. Evidence expires after 15 minutes. Refresh the request if it expires; approval cannot override failed checks.

The demo has no real purchase integration. A real transaction would also require verifying the actual payable total and all required product attributes immediately before action.

## Evidence and recovery

[Presenter verification](../demos/VERIFICATION.md) records earlier live executions. [Eight screenshots](../demos/screenshots/README.md) provide four views per demo. The CrewAI result screenshot is a recorded replay; the n8n approval screenshot came from a fresh run and the simulation output from an earlier successful execution. Historical item prices are not current price guarantees.

If marketplace pages block automation, show the source failures or NO_MATCH. Use recorded evidence only with its replay label. Do not substitute fixtures as a live result.

Run the six control checks with `demos/.venv/bin/python demos/test_boundaries.py` from the workshop folder. Stop the services with `./demos/stop.sh`.
