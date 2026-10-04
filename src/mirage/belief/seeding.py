"""Deterministic seed derivation for independent belief RNG streams."""

from __future__ import annotations

import numpy as np


def belief_stream_seed(episode_seed: int) -> int:
    return int(
        np.random.SeedSequence([episode_seed, 0x42454C46]).generate_state(
            1, dtype=np.uint32
        )[0]
    )
