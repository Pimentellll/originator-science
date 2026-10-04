"""fastapi is a shared optional dependency: everything except create_app must import without it."""

import subprocess
import sys


def test_core_layers_import_without_fastapi():
    program = (
        "import sys\n"
        "for n in ('fastapi', 'starlette', 'uvicorn', 'httpx'):\n"
        "    sys.modules[n] = None\n"
        "import mirage.api, mirage.api.service, mirage.api.dto\n"
        "import mirage.provenance, mirage.evaluation.campaign\n"
        "print('ok')\n"
    )
    out = subprocess.run([sys.executable, "-c", program], capture_output=True, text=True)
    assert out.returncode == 0 and out.stdout.strip() == "ok", out.stderr
