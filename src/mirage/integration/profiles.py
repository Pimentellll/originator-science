"""Named integration profiles for scientifically scoped MIRAGE campaigns."""

from __future__ import annotations

from enum import Enum

from mirage.environments.binder.scenarios import BinderWorldMode


class ScientificProfile(str, Enum):
    """Integration-level campaign specialisations; contracts remain generic."""

    RECEPTOR_BINDER_RESCUE = "RECEPTOR_BINDER_RESCUE"


def default_world_mode(profile: ScientificProfile) -> BinderWorldMode:
    """Default scenario for a profile, intentionally not policy-visible."""
    if profile == ScientificProfile.RECEPTOR_BINDER_RESCUE:
        return BinderWorldMode.COMPOUND_FAILURE
    raise ValueError(f"unsupported scientific profile {profile!r}")
