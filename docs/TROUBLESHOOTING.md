# Troubleshooting

Start with the doctor. It checks every item below and prints the exact fix for whatever fails.

```bash
./mirage doctor          # exit code 0 = ready
./mirage doctor --json   # machine-readable
```

Logs for a running stack are in `.local/mirage/logs/api.log` and `web.log`. When a service fails to start,
`./mirage demo` prints the last 25 lines of the relevant log for you.

Contents: [uv](#uv-is-not-installed) · [uvicorn](#uvicorn-or-another-python-package-is-missing) ·
[wrong virtualenv](#wrong-virtualenv) · [port 8000](#port-8000-is-already-occupied) · [port 5173](#port-5173-is-already-occupied) ·
[PowerShell](#i-pasted-a-command-into-powershell-instead-of-wsl) · [Node](#node-is-missing-or-too-old) · [npm](#npm-install-fails) ·
[stale processes](#stale-frontend-or-backend-process) · [browser](#the-browser-does-not-open) · [WSL networking](#wsl-and-localhost) ·
[API ok, frontend offline](#api-is-healthy-but-the-frontend-is-offline) · [frontend ok, API unreachable](#frontend-is-running-but-the-api-is-unreachable) ·
[known test failures](#known-test-failures)

---

## uv is not installed

`./mirage setup` installs `uv` for you into `~/.local/bin` (official installer, no sudo, no global Python changes). If the
download is blocked (corporate proxy, offline), setup says so and falls back to `python -m venv` + `pip`, which is slower
but installs exactly the same packages.

To install uv yourself:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
exec bash          # or open a new terminal so ~/.local/bin is on PATH
./mirage setup
```

If you see `HTTP Error 403` from the installer when it is fetched with Python's own HTTP client, that is the installer
host rejecting an unknown User-Agent. MIRAGE uses `curl` when present for exactly that reason.

## uvicorn (or another Python package) is missing

Symptom: `ModuleNotFoundError: No module named 'uvicorn'` when starting the API. It means you are using a virtualenv
that was not built from this repository's `pyproject.toml` (an old or hand-made `.venv`).

```bash
./mirage setup --force      # re-resolves dependencies from pyproject.toml into .venv
./mirage doctor
```

Manual equivalent: `.venv/bin/python -m pip install -e ".[dev,rl]"`. Never `pip install` into the system Python.

## Wrong virtualenv

Symptoms: `./mirage doctor` shows `MIRAGE import ... imports a different checkout`, or tests exercise code from another
copy of the repo. This happens when `.venv` was created in another checkout or git worktree and copied or reused.

```bash
rm -rf .venv && ./mirage setup
```

`./mirage` always uses `<repo>/.venv` and ignores any virtualenv you have activated in your shell.

## Port 8000 is already occupied

`./mirage demo` never kills a program it did not start. It tells you what holds the port and moves to the next free one
(for example 8001); the cockpit's proxy is pointed at whichever port the API actually got.

Find the owner yourself:

```bash
ss -ltnp 'sport = :8000'          # or: lsof -nP -iTCP:8000 -sTCP:LISTEN
```

If it is an old MIRAGE API from a previous manual start (`python scripts/serve_api.py ...`), stop that process:

```bash
kill <pid>
```

If it was started by `./mirage`, use `./mirage stop`. To pick ports explicitly:
`./mirage demo --port 8100 --frontend-port 5180`.

## Port 5173 is already occupied

Same as above. A leftover Vite server is the usual cause. `./mirage stop` stops the ones it started; for a stray one:

```bash
ss -ltnp 'sport = :5173'
kill <pid>
```

Vite is started with `--strictPort`, so it never silently hops to another port behind your back; the launcher chooses the
port and prints the real URL.

## I pasted a command into PowerShell instead of WSL

Symptoms: `./mirage : The term './mirage' is not recognized`, `bash: command not found` in PowerShell, or paths that
begin with `C:\`. MIRAGE runs inside WSL2 Ubuntu, not in PowerShell or cmd.

1. Open the **Ubuntu** app (or run `wsl -d Ubuntu-24.04` from PowerShell). The prompt should look like `you@host:~$`.
2. Work inside the Linux filesystem (`~/...`), not `/mnt/c/...` (slow, and file permissions break).
3. Run the commands there: `cd ~/originator-science && ./mirage demo`.

No WSL yet: in an administrator PowerShell run `wsl --install -d Ubuntu-24.04`, reboot, then open Ubuntu.

## Node is missing or too old

The cockpit needs Node **20.19+ or 22.12+** (Vite 8). Check with `node --version`.

```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
exec bash
nvm install 22
./mirage setup
```

macOS: `brew install node@22`. Backend only, without Node: `./mirage setup --skip-frontend`.

Node installed on the Windows side is not visible inside WSL. If `which node` prints `/mnt/c/...`, install Node inside
Ubuntu as above.

## npm install fails

```bash
rm -rf frontend/node_modules
./mirage setup --force
```

Still failing:

- `ETIMEDOUT` / `ECONNRESET`: network or proxy. Set `npm config set proxy ...` or retry on another network.
- `EACCES`: you ran npm with sudo once; fix ownership: `sudo chown -R "$USER" frontend ~/.npm`.
- `engine` warnings or syntax errors from tooling: Node is too old, see above.
- The log of the failed install is printed by npm (`~/.npm/_logs/`).

## Stale frontend or backend process

Symptoms: the UI shows old behaviour, `/version` shows an old commit, the new port is not what you expected.

```bash
./mirage stop                 # stops only processes recorded in .local/mirage/pids, after verifying their command line
./mirage doctor               # the port checks show anything else still listening
```

`stop` refuses to touch a recycled PID or any process whose command line is not this checkout's `serve_api.py` /
`vite`. It never runs `killall`.

## The browser does not open

The demo prints the URL; open it manually. Auto-open order: WSL → `wslview`, then `powershell.exe Start-Process`;
Linux → `xdg-open` (needs a desktop session); macOS → `open`. Headless servers, SSH sessions and containers have no browser to
open, which is expected.

```bash
./mirage demo --no-browser          # print the URL only
sudo apt install wslu               # gives WSL the wslview helper
```

## WSL and localhost

Windows reaches servers in WSL2 through `localhost` forwarding, which is on by default. MIRAGE binds to `127.0.0.1`
inside WSL, which that forwarding supports.

If `http://localhost:5173` does not load from a Windows browser:

1. Check inside WSL first: `curl -s http://127.0.0.1:5173/ | head -3`. If that works, the server is fine.
2. Try `http://127.0.0.1:5173/?transport=live` instead of `localhost` (some setups resolve `localhost` to IPv6 first).
3. In `%UserProfile%\.wslconfig` make sure `localhostForwarding=true` is not disabled, then `wsl --shutdown` from PowerShell
   and start Ubuntu again.
4. VPN and corporate security clients sometimes break the forwarding; the same URL usually works from a browser inside WSLg.

## API is healthy but the frontend is offline

```bash
curl -s http://127.0.0.1:8000/health          # {"status":"ok",...} means the API is fine
tail -30 .local/mirage/logs/web.log           # why Vite did not start
```

Usual causes: Node too old (see above), `frontend/node_modules` missing (`./mirage setup`), or the Vite port taken
(`./mirage doctor`).

## Frontend is running but the API is unreachable

The cockpit shows "Cannot load episode" with `Cannot reach the MIRAGE API at /api/...`. The browser talks to Vite, and Vite
proxies `/api/*` to the API. Test each hop:

```bash
curl -s http://127.0.0.1:8000/health           # the API itself
curl -s http://127.0.0.1:5173/api/health       # through the Vite proxy
tail -30 .local/mirage/logs/api.log
```

- First fails: the API is down or on another port. `./mirage demo` always points the proxy at the API's real port; if
  you started Vite by hand, set `MIRAGE_API_PROXY=http://127.0.0.1:<port>` (use `127.0.0.1`, not `localhost`, which
  Node can resolve to `::1`).
- Second fails but first works: the proxy target is wrong. Restart with `./mirage stop && ./mirage demo`.

The cockpit's **System** tab (`#/diagnostics`) shows the same hops.

## Known test failures

`./mirage test` separates software failures from scientific validation gates. On `main` today two gates are **NOT
PASSED**, and they are documented, not bugs in your change:

| Gate | Why | Where it is recorded |
|---|---|---|
| B4A convergence gate | the declared posterior-convergence criterion is not met at any tested particle count; the gate was not relaxed | [validation/B4A_CONVERGENCE_RESULTS.md](validation/B4A_CONVERGENCE_RESULTS.md) |
| V2 preregistration lock | the hash lock no longer matches `evaluation/campaign/truth.py` after the A5 semantics change | [evaluation/BINDER_RESCUE_V2_STATUS.md](evaluation/BINDER_RESCUE_V2_STATUS.md) |

Exit code 2 from `./mirage test` means "software is clear, a validation gate is not passed". Exit code 1 means a software
failure.
