#!/usr/bin/env python3
"""Start the public MIRAGE receptor-binder API used by the frontend."""
import argparse
import os
from pathlib import Path

import uvicorn

from mirage.api.app import create_app
from mirage.environments.binder import BinderWorldMode
from mirage.integration import make_receptor_binder_service
from mirage.provenance import PublicRecordStore

parser=argparse.ArgumentParser(description="Run the public MIRAGE Binder API.")
parser.add_argument("--host",default="127.0.0.1")
parser.add_argument("--port",type=int,default=8000)
parser.add_argument("--records",type=Path,default=Path(".local/mirage-api"))
parser.add_argument("--scenario",choices=tuple(x.value for x in BinderWorldMode),default=BinderWorldMode.COMPOUND_FAILURE.value)
parser.add_argument("--growth-results",type=Path,default=Path("experiments/results"))
args=parser.parse_args()
service=make_receptor_binder_service(PublicRecordStore(args.records),scenario=BinderWorldMode(args.scenario),code_version="h1")
uvicorn.run(
    create_app(
        service,
        aggregate_token=os.environ.get("MIRAGE_EVAL_TOKEN"),
        growth_results_root=args.growth_results,
        cors_origins=("http://localhost:5173", "http://localhost:4173"),
    ),
    host=args.host,
    port=args.port,
)
