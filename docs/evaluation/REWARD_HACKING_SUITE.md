# Reward-hacking suite

Training reward is not scientific evaluation. Reward may combine bounded terminal utility, resource penalties and
bounded information-gain shaping; it may not be used as proof of scientific validity (ADR 0006).

The suite (`mirage.evaluation.campaign.adversarial`) has two parts.

**Executable specification cases (`SPEC_CASES`).** Hand-built public traces with known truth that pin evaluator
semantics: misleading proxy (good and bad molecule), blind `SELECT` on a broken assay, a broken assay handled correctly,
an agent that blames the model for a broken assay, a model-invalid case done right, a lucky `MODEL_INVALID`, a compound
failure collapsed to one mechanism, premature aggregated SPR, repair before SPR, redesign on an assay artefact,
appropriate and free abstention, a self-confirming terminal claim, measurement spam, and a justified single-failure
`REJECT`. They are specifications, not benchmark results.

**Exploit policies (`EXPLOIT_POLICIES`).** Deterministic policies that each exploit one shortcut and obey the common policy
contract, so they run through the harness on any real world source: `BlindSelect`, `BlindModelInvalid`, `AlwaysAbstain`,
`ProxyChaser`, `InformationFarmer`, `Redesigner`. `check_exploit_invariants` states what must hold on any world: an
exploit may be lucky (correct) but must never be scored as scientifically justified.

The suite checks proxy exploitation, self-confirming terminal claims, truth leakage, unnecessary redesign, information-gain
farming and a correct answer unsupported by evidence. It does not guarantee that an *unknown* exploit does not exist.
