# Run n8n locally on macOS and Windows

This guide installs the n8n editor and explains how to import the workshop workflows. The workshop uses **n8n 2.43.7**. Use that version to reproduce the session; it is a compatibility pin, not a claim that it is the latest release. For ongoing use, review current releases and security updates.

## Prerequisites

- An internet connection for the initial download and a modern browser.
- Terminal on macOS, or PowerShell on Windows.
- Port **5678** available. Run only one n8n instance on that port.
- Choose **one** installation method below. Basic n8n installation does not require Python, Git, or an AI API key. Individual integrations may need credentials.

| Method | Install first | Best fit |
| --- | --- | --- |
| Node.js / npm | [Node.js 24.x](https://nodejs.org/en/download), including npm | Reproducing this workshop directly on your computer |
| Docker | Docker Desktop, running with Linux containers | An isolated installation with persistent storage |

The [n8n npm documentation](https://docs.n8n.io/deploy/host-n8n/install-options/install-with-npm.md) currently lists Node.js 20.19–24.x and notes npm installation is deprecated from n8n 3.0. This guide deliberately pins the workshop's 2.x version. Use Docker for a new installation intended to follow future releases.

## Option A: Node.js / npm

### macOS

1. Install Node.js **24.x** from the official download page.
2. Open a new Terminal window and verify:

   ```bash
   node --version
   npm --version
   ```

3. Start the workshop version:

   ```bash
   N8N_LISTEN_ADDRESS=127.0.0.1 npx n8n@2.43.7
   ```

### Windows

1. Install Node.js **24.x** using the official Windows installer, including npm and its PATH option.
2. Open a new PowerShell window and verify:

   ```powershell
   node --version
   npm.cmd --version
   ```

3. Start the workshop version:

   ```powershell
   $env:N8N_LISTEN_ADDRESS = "127.0.0.1"
   npx.cmd n8n@2.43.7
   ```

The first run downloads n8n and may ask permission to install the package. Keep the terminal open while using it. Stop with **Ctrl+C**; run the same command to start again. n8n normally stores its data in your user profile's `.n8n` directory unless you configure a different user folder. Keep that directory, including its encryption key, when backing up.

## Option B: Docker Desktop

### macOS prerequisites

Install [Docker Desktop for Mac](https://docs.docker.com/desktop/setup/install/mac-install/), selecting **Apple silicon** or **Intel** to match your computer. Docker lists a supported macOS release and at least 4 GB RAM as prerequisites. Open Docker Desktop and wait until the engine is running.

### Windows prerequisites

Follow [Docker Desktop for Windows](https://docs.docker.com/desktop/setup/install/windows-install/) for the supported Windows release and hardware requirements. For the WSL 2 backend, enable hardware virtualization and use WSL 2.1.5 or later; Docker lists at least 8 GB system RAM. If WSL is missing, run the following in an administrator PowerShell, then restart if requested:

```powershell
wsl --install
wsl --update
wsl --version
```

Install and open Docker Desktop with its WSL 2 backend. Use **Linux containers** for n8n.

### Start on either operating system

Run these commands in Terminal or PowerShell. The long command is intentionally one line so it works in both shells:

```text
docker --version
docker info
docker volume create iisc_n8n_data
docker run -d --name iisc-n8n -p 127.0.0.1:5678:5678 -e GENERIC_TIMEZONE=Asia/Kolkata -e TZ=Asia/Kolkata -e N8N_ENFORCE_SETTINGS_FILE_PERMISSIONS=true -v iisc_n8n_data:/home/node/.n8n docker.n8n.io/n8nio/n8n:2.43.7
docker logs --tail 50 iisc-n8n
```

This basic editor setup uses a named volume for its database and configuration. It does not install the optional n8n Assistant stack. See the [official Docker documentation](https://docs.n8n.io/deploy/host-n8n/install-options/install-with-docker.md) and [Compose guide](https://docs.n8n.io/deploy/host-n8n/install-options/install-using-docker-compose.md) for other deployment options.

For subsequent sessions:

```text
docker stop iisc-n8n
docker start iisc-n8n
docker ps
```

Keep the `iisc_n8n_data` volume to retain your workflows and credentials. Restarting the container does not delete it.

## Open n8n and verify the installation

1. Open <http://localhost:5678> and complete the local owner-account setup.
2. Create a workflow with a **Manual Trigger** connected to **Edit Fields (Set)**.
3. Add a field such as `message` with the value `Hello from n8n`.
4. Execute the workflow and confirm that the output contains your message.

This verifies the editor and workflow execution without external accounts.

## Import the workshop JSON

Download this repository as a ZIP and extract it, or clone it if you use Git. In n8n, create a workflow, open its workflow menu, choose **Import from File**, and select:

- [complete-workflow.json](complete-workflow.json): the finished shopping workflow.
- [starter-workflow.json](starter-workflow.json): the exercise version with the browser-search node intentionally omitted.

Save the import. Publish/activate it when you want its production form URL to work; a test form needs its trigger listening in the editor.

### Running the full shopping demo

**Importing the JSON alone does not start the shopping backend.** The HTTP nodes call the browser/ranking service on port **8002** and the simulated action service on **8001**. Those services need Python 3.12, the repository dependencies, Google Chrome, and your own signed-in Codex CLI. Follow the [workshop setup instructions](../../README.md#setup).

The supplied `start.sh` / `manage.py` launcher targets macOS/Linux and is **not a native Windows launcher**. The full shopping demo has not been verified on a clean Windows installation. The n8n editor instructions above are separate from that full demo setup.

For Docker Desktop, `127.0.0.1` inside a container means the container itself. The imported HTTP URLs must use `host.docker.internal` to reach a backend on your host, and that backend must listen on an interface reachable from Docker. The supplied launcher binds it to host loopback, so importing unchanged JSON into Docker is not sufficient. Use the native workshop setup to reproduce the complete demo without network changes.

## Troubleshooting

| Problem | What to check |
| --- | --- |
| `node`, `npm`, or `npx` not found | Reopen the terminal after installing Node.js; check PATH and `node --version`. |
| PowerShell says scripts are disabled | Use `npm.cmd` and `npx.cmd` as shown; no execution-policy change is needed. |
| Docker cannot connect to its daemon | Open Docker Desktop and wait for its engine to start. |
| Port 5678 is already in use | Stop the other instance, or map Docker to `127.0.0.1:5679:5678` and open port 5679. |
| Container name already exists | Use `docker start iisc-n8n` rather than running the creation command again. |
| Form returns 404 | Confirm the workflow is published/active and use its current production URL. |
| Shopping HTTP nodes report connection refused | Start both backend services; check ports 8001/8002 and the Docker networking note above. |
| Approval link expired | Submit a fresh shopping request; the demo's approval wait expires after 15 minutes. |

Documentation checked: **30 October 2026**. Installation commands were reviewed against the sources above; a fresh macOS/Windows installation was not performed as part of writing this guide.
