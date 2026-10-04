# Developer setup

```bash
git clone https://github.com/Pimentellll/originator-science.git
cd originator-science
./mirage demo
```

That is the whole setup. `./mirage` creates `.venv`, installs the Python and frontend dependencies, runs health checks,
starts the API and the cockpit, waits until both are healthy, and opens your browser. Everything project-specific lives in
`.venv` and `frontend/node_modules`; runtime state lives in `.local/mirage/` (git-ignored).

## Supported platforms

| Platform | Status |
|---|---|
| Ubuntu 24.04 | primary |
| WSL2 Ubuntu (24.04) | primary; this is what the project is developed on |
| Other Linux | supported; Python 3.11+ (uv can fetch one) and Node 20.19+/22.12+ needed |
| macOS | secondary: same commands, less tested |
| Windows (native PowerShell / cmd) | **not supported**. Use WSL2: `wsl --install -d Ubuntu-24.04`, then work in the Ubuntu terminal |

## What you need before you start

| Tool | Needed for | If missing |
|---|---|---|
| `git` | everything | `sudo apt install git` |
| `python3` (any 3.9+) | starts the launcher | `sudo apt install python3 python3-venv` |
| Python 3.11+ | the project itself | `./mirage setup` asks uv to fetch one if the system has none |
| Node 20.19+ or 22.12+ and npm | the cockpit | see [TROUBLESHOOTING](TROUBLESHOOTING.md#node-is-missing-or-too-old) (`nvm install 22`) |
| `uv` | fast installs | installed automatically to `~/.local/bin`; falls back to `venv` + `pip` |

`./mirage` never needs `sudo`, never changes global Python packages, and never installs project packages globally.

## Commands

| Command | What it does |
|---|---|
| `./mirage demo` | set up if needed, start API + cockpit, open the browser. `Ctrl+C` stops both |
| `./mirage dev` | the same without opening a browser, with readable `[API]` / `[WEB]` prefixed logs and Vite hot reload |
| `./mirage setup` | create `.venv`, install dependencies. Idempotent: a second run reports "already installed" and exits quickly. `--force` reinstalls, `--skip-frontend` skips npm |
| `./mirage doctor` | diagnose the environment and print the exact fix for each failure. Exit 0 = ready. `--json` for machines |
| `./mirage test` | grouped test run; `--quick` (about 10 s) and `--scientific` variants |
| `./mirage smoke` | the deterministic H0 campaign plus the trust-boundary smoke |
| `./mirage benchmark-dev` | a small benchmark on the *development* seed split into `.local/benchmark-dev`. Never touches held-out seeds or `results/` |
| `./mirage stop` | stop MIRAGE-owned API/cockpit processes (verified by command line). Never `killall` |
| `./mirage clean-runtime` | delete `.local/`, `.pytest_cache`, `frontend/dist`. Keeps `results/`, checkpoints and tracked files. `--all` also deletes `.venv` and `node_modules` after confirmation |

### `demo` / `dev` options

```bash
./mirage demo --scenario COMPOUND_FAILURE      # | SINGLE_FAILURE | ASSAY_FAILURE | MODEL_FAILURE | MIXED
./mirage demo --scenario-version SEMANTICS_V2  # default; BASELINE_V1 is the frozen historical baseline
./mirage demo --policy rescue_planner          # | greedy_eig | fixed_pipeline | random
./mirage demo --seed 9
./mirage demo --port 8000 --frontend-port 5173 # preferred ports; another free one is used if busy
./mirage demo --no-browser
./mirage demo --guided                         # open straight into the guided demo
./mirage demo --docker                         # fallback, see below
```

New live demonstrations default to `SEMANTICS_V2`. Baseline V1 stays explicitly selectable; its results are frozen.
The scenario is **orchestration metadata** chosen by the person running the demo. It is never sent to a policy and never
appears in the public record or replay (only the semantics version does).

## One dependency path

`pyproject.toml` is the single source of truth. `./mirage setup` runs the equivalent of:

```bash
uv venv .venv
uv pip install --python .venv/bin/python -e ".[dev,rl]"   # on Linux with the CPU-only PyTorch index (about 200 MB, not 2.5 GB of CUDA)
npm ci --prefix frontend
```

Manual fallback with no uv:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev,rl]"
cd frontend && npm ci
```

`fastapi`, `uvicorn` and `httpx` are core dependencies (the documented runtime needs them); `pytest` is in `dev`; Gymnasium,
Stable-Baselines3, sb3-contrib and PyTorch are in `rl`. Add a dependency to `pyproject.toml` and re-run `./mirage setup`.

## Running pieces by hand

You should not need these, but they are what `./mirage` runs:

```bash
# API (note PYTHONPATH=src; ./mirage sets it for you)
PYTHONPATH=src .venv/bin/python scripts/serve_api.py --port 8000 --scenario COMPOUND_FAILURE --scenario-version SEMANTICS_V2
# cockpit
cd frontend && MIRAGE_API_PROXY=http://127.0.0.1:8000 npm run dev      # http://localhost:5173/?transport=live
# tests
PYTHONPATH=src .venv/bin/python -m pytest -q
cd frontend && npm run typecheck && npm run lint && npm test && npm run build
```

The API serves the per-episode verdict (`/benchmarks/episodes/{id}`) only when `MIRAGE_EVAL_TOKEN` is set. `./mirage demo`
generates a throwaway token per run and gives it to the API and to the Vite proxy through the environment only; it is never
printed, never in a URL, and never in the browser bundle.

## Tests

```bash
./mirage test --quick        # ~10 s: contracts, trust boundary, API, E2E over a real socket, typecheck + frontend unit tests
./mirage test                # every software group, then the scientific validation gates (a few minutes)
./mirage test --scientific   # only the validation gates and benchmark invariants
./mirage test --list         # what each group covers
```

pytest stays the authoritative runner; the wrapper groups its results. Software groups report `PASS` / `FAIL`. Scientific
validation gates report `PASS` or `NOT PASSED` and are never folded into software results. Exit codes: `0` all clear, `1` a
software failure, `2` software clear but a validation gate is not passed. Two gates are known to be unmet on `main`
([TROUBLESHOOTING](TROUBLESHOOTING.md#known-test-failures)).

## Layout of the launcher

| Path | Role |
|---|---|
| `mirage` | Bash entry point: finds the repo root from any directory, picks a Python, hands over |
| `scripts/mirage_cli.py` | command dispatch, `setup`, `stop`, `clean-runtime`, `smoke` (standard library only) |
| `scripts/supervisor.py` | `demo` / `dev`: ports, process groups, readiness checks, browser, clean shutdown |
| `scripts/doctor.py`, `scripts/doctor_checks.py` | diagnostics (outer, stdlib) and the project-side checks run inside `.venv` |
| `scripts/run_tests.py` | the grouped test wrapper |
| `scripts/mirage_env.py` | shared helpers: platform, ports, pid registry, uv/venv/node discovery |
| `.local/mirage/{pids,logs,stamps}` | runtime state (git-ignored) |

## Docker (fallback only)

`./mirage demo --docker` uses `compose.yaml`. It is a fallback for machines where Node or Python cannot be installed; native
is the primary path. See the note in [DEMO_GUIDE](DEMO_GUIDE.md#docker-fallback) about its verification status.
