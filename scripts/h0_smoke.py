"""Run the deterministic H0 Binder campaign without an HTTP server."""

from __future__ import annotations

import tempfile
from pathlib import Path

from mirage.environments.binder import BinderWorldMode
from mirage.integration import CampaignController, ScientificProfile
from mirage.provenance import PublicRecordStore, Replay


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="mirage-h0-") as directory:
        controller = CampaignController(PublicRecordStore(Path(directory)))
        controller.reset(9, BinderWorldMode.COMPOUND_FAILURE, ScientificProfile.RECEPTOR_BINDER_RESCUE, "rescue_planner")
        trace = []
        for _ in range(6):
            step = controller.step()
            trace.append(step.dto.event.action.action_type.value)
            if step.terminal:
                break
        record = controller.record()
        evaluation = controller.evaluate()
        print(" -> ".join(trace))
        print(f"events={len(record.events)} replay_frames={len(tuple(Replay(record)))}")
        print(f"scenario={evaluation.scenario_class} regime={evaluation.regime} justified={evaluation.justified}")


if __name__ == "__main__":
    main()
