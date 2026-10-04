#!/usr/bin/env python3
"""Start the public MIRAGE receptor-binder API used by the frontend.

Normally launched by ``./mirage demo`` / ``./mirage dev``. Scenario and semantics are
orchestration choices for the human running the demo; policies never see them.

The per-episode verdict route (``/benchmarks/episodes/{id}``) is enabled only when
``MIRAGE_EVAL_TOKEN`` is set; ``./mirage`` generates a throwaway local token per run.
"""
import argparse
import os
from pathlib import Path

import uvicorn

from mirage.api.app import create_app
from mirage.api.meta import code_version
from mirage.environments.binder import BinderWorldMode
from mirage.environments.binder.scenarios import BinderScenarioVersion
from mirage.integration import make_receptor_binder_service
from mirage.integration.catalogue import receptor_binder_catalogue, resolve_world
from mirage.provenance import PublicRecordStore

parser = argparse.ArgumentParser(description="Run the public MIRAGE Binder API.")
parser.add_argument("--host", default="127.0.0.1")
parser.add_argument("--port", type=int, default=8000)
parser.add_argument("--records", type=Path, default=Path(".local/mirage-api"))
parser.add_argument("--scenario", default=BinderWorldMode.COMPOUND_FAILURE.value, help="world mode (e.g. COMPOUND_FAILURE) or showcase id")
parser.add_argument("--scenario-version", choices=tuple(v.value for v in BinderScenarioVersion), default=BinderScenarioVersion.SEMANTICS_V2.value)
parser.add_argument("--cors-origin", action="append", default=None, help="repeatable; defaults to the Vite dev origins")
parser.add_argument("--growth-results", type=Path, default=Path("experiments/results"), help="MIRAGE-Bio growth results root (gated by the eval token)")
parser.add_argument("--log-level", default="info")
args = parser.parse_args()

world = resolve_world(args.scenario, BinderWorldMode.COMPOUND_FAILURE)
version = BinderScenarioVersion(args.scenario_version)
service = make_receptor_binder_service(PublicRecordStore(args.records), scenario=world, code_version=code_version(), scenario_version=version)
token = os.environ.get("MIRAGE_EVAL_TOKEN") or None
origins = tuple(args.cors_origin or ("http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:4173"))
app = create_app(service, aggregate_token=token, growth_results_root=args.growth_results, cors_origins=origins, catalogue=receptor_binder_catalogue(service, world, version))
uvicorn.run(app, host=args.host, port=args.port, log_level=args.log_level)
