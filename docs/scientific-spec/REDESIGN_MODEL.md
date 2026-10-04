# Redesign model

Redesign is a **simulator-backed, synthetic** transition. It makes no claim to predict real mutations, and no sequence
exists anywhere in the system.

Each operation creates a new public `Candidate` with id `binder-NNN`, generation + 1 and the active candidate as parent,
makes the child active, and privately samples the child's factorised state from the parent's with a seeded transition
(`BinderPredictiveModel.redesign`, also used by the belief engine as its transition kernel):

| Action | Expected effect (Gaussian shifts, then clipped to valid ranges) |
|---|---|
| `REDESIGN_STABILITY` | stability +0.24 (σ 0.07); monomer fraction +0.06 (σ 0.04) |
| `REDESIGN_SOLUBILITY` | monomer fraction +0.25 (σ 0.07); stability −0.02 (σ 0.04) |
| `REDESIGN_INTERFACE` | `log_kd` −0.45 (σ 0.15); `log_koff` −0.35 (σ 0.15); stability −0.03 (σ 0.04) |

Epitope, developability liability, assay validity and model validity are inherited unchanged. A redesign therefore
cannot repair an epitope, a developability liability, a broken assay or an invalid model; the evaluator counts a
redesign as *unnecessary* when its objective addresses no truly failing factor of the parent. Its mapping
(`REDESIGN_ADDRESSES`) lists epitope failure under `REDESIGN_INTERFACE`, although the transition leaves the epitope
unchanged, so an interface redesign of an epitope-failing parent is *not* flagged unnecessary yet cannot repair it. This
is a known inconsistency between the evaluator's bookkeeping and the simulator.

Each redesign costs 2.0 budget, 1.0 sample and 1.0 time. The interface is pluggable so a future sequence or structure
engine could implement *how* proposals are generated while MIRAGE continues to decide *what to improve and why*;
none is implemented.
