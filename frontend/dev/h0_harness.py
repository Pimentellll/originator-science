"""DEV HARNESS (frontend-owned, not backend code): launches the H0 backend for the live smoke test.

    MIRAGE_BACKEND_ROOT=/path/to/checkout-of-feat/mirage-integration \
    MIRAGE_EVAL_TOKEN=<any-local-value>  python dev/h0_harness.py     # serves on :8100

Needs fastapi, uvicorn, numpy, pydantic in the Python environment.

Uses H0's own make_receptor_binder_service + the frozen public API (create_app) unchanged.
Harness additions (flagged, because H0 does not ship them):
  * registers `rescue_planner` and `greedy_eig` with the service (H0 registers only random / fixed_pipeline);
  * GET /benchmarks/episodes/{id}  (HARNESS-ONLY, token-gated like /benchmarks): correct-vs-justified verdict from
    H0's own CampaignEvaluator + _BinderOracle, only once the episode is terminal. H0 has no such endpoint. It must live
    under /benchmarks because the public leak guard forbids the keys `correct` / `justified` on every other route.
"""
import os, sys, tempfile
ROOT = os.environ["MIRAGE_BACKEND_ROOT"]
sys.path[:0] = [ROOT + "/src"]

import uvicorn
from fastapi import HTTPException
from mirage.api.app import create_app
from mirage.belief import ParticleBelief
from mirage.integration import make_receptor_binder_service
from mirage.integration.controller import BinderBeliefSession, _BinderOracle
from mirage.integration.rescue_policy import ReceptorRescuePlannerPolicy
from mirage.evaluation.campaign import CampaignEvaluator
from mirage.policies import GreedyEIGPolicy
from mirage.provenance import PublicRecordStore

STORE = os.environ.get("MIRAGE_STORE", tempfile.mkdtemp(prefix="mirage-h0-"))
service = make_receptor_binder_service(PublicRecordStore(STORE), code_version="integration@4747deb")

# GreedyEIG needs a handle on ITS episode's belief. EpisodeService builds the policy, then the belief,
# in sequence per request; bind each policy to the next belief created (a per-episode box, not a global).
import collections
PENDING = collections.deque()
_orig_belief = service._belief_factory
def _belief(seed, state):
    s = _orig_belief(seed, state)
    if PENDING:
        PENDING.popleft()["s"] = s
    return s
service._belief_factory = _belief
def _greedy():
    box = {}
    PENDING.append(box)
    return GreedyEIGPolicy(BinderBeliefSession(0).model, lambda: box["s"].belief, seed=0, n_samples=32)
service._policies["rescue_planner"] = ReceptorRescuePlannerPolicy
service._policies["greedy_eig"] = _greedy

app = create_app(service, cors_origins=["http://localhost:5173", "http://localhost:4173"])

SAFE = ("decision", "correct", "justified", "lucky_correct", "supported_but_wrong", "unnecessary_redesigns",
        "spr_health_lost", "premature_aggregated_spr", "compound_recognized", "assay_invalid_detected", "model_invalid_detected")

import hmac
from fastapi import Header
TOKEN = os.environ["MIRAGE_EVAL_TOKEN"]  # required; any local value

@app.get("/benchmarks/episodes/{episode_id}")
def evaluation(episode_id: str, x_mirage_eval_token: str | None = Header(default=None)):
    if x_mirage_eval_token is None or not hmac.compare_digest(x_mirage_eval_token.encode(), TOKEN.encode()):
        raise HTTPException(403, "not authorised")
    live = service._live.get(episode_id)
    if live is None or not live.recorder.finished:
        raise HTTPException(409, "evaluation is available only after the episode is terminal")
    ev = CampaignEvaluator().evaluate(live.recorder.finish(), _BinderOracle(live.env))
    raw = ev.model_dump(mode="json")
    out = {k: raw[k] for k in SAFE if k in raw}
    out.update(episode_id=episode_id, evaluator_version=raw["evaluator_version"],
               justification_checks=[{"name": c["name"], "passed": c["passed"]} for c in raw["justification_checks"]])
    return out

if __name__ == "__main__":
    print("H0 harness; store:", STORE, flush=True)
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", "8100")), log_level="warning")
