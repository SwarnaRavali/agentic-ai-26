# Live verification — 19 October 2026, IST

Both demos ran on this machine using the signed-in Codex CLI and actual public marketplace pages. Results below are recorded observations, not current price guarantees.

## CrewAI

- Three-role live crew: parsed the ₹1,000 request, rejected insufficient colour evidence, returned NO_MATCH; independent validation passed.
- Single-agent live crew: one Codex call, READY_FOR_APPROVAL; independent validation passed.
- Manager/workers with shared context and adversarial review: five Codex calls, READY_FOR_APPROVAL; independent validation passed.
- Isolated peers with final policy synthesis: three Codex calls, READY_FOR_APPROVAL; independent validation passed.
- Successful runs selected an observed BIRDE item from Myntra at ₹234. This was an observed item price; checkout total and other unknowns remained explicit.
- Sixteen topology/communication/reviewer configurations with role overrides generated syntactically valid Python and valid context references.

Recorded JSON files are in `runs/crew-*.json`. Only outputs labeled `evidence_mode: live_browser` appear in the saved-live-run replay UI. Earlier fixture-based tests are not represented as live evidence.

The CrewAI UI's HTML and JavaScript were syntax-checked and its APIs exercised. The browser tool's saved permission denied automated access to port 8765, so the CrewAI page has not received a visual browser walkthrough.

## n8n

The completed eleven-node workflow is imported, published, and browser-inspected. Its local owner setup was completed by the user.

Browser-verified executions:

- Execution 2: live search, real Codex ranking, validation, durable Human Approval wait, Cancel, Cancelled terminal. The simulated action did not run.
- Execution 3: a fresh live search and Codex ranking, durable approval wait, explicit simulated approval, local action endpoint, Order Confirmation. Reference `DEMO-LIVE-1792351609025`. Response: `payment_taken: false`, `marketplace_contacted: false`. Freshness and proposal identity were rechecked.
- Execution 4: an explicit ₹1 budget test returned No eligible recommendation without reaching the action node.

Screenshots are in `runs/n8n-*.png`. No marketplace login, cart, payment, or purchase occurred.

## Controls

Six regression checks passed: explicit approval required, changed proposal rejected, expired evidence rejected, invalid host/budget rejected, missing colour rejected, unknown proposal rejected. The live simulated endpoint also rejected `approved: false`, accepted the explicit simulated test, and reused the same record for a duplicate proposal (idempotency).

Services are bound to loopback. Proposals and simulated records persist locally across service restarts. Browser source failures and optional unknowns remain visible. The app contains no actual commerce integration.
