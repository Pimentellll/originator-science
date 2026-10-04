# Binder BioPOMDP

The MIRAGE Binder BioPOMDP models rescue and maturation of a synthetic de novo miniprotein binder after poor downstream function. It is an in-development, seeded simulator; its numerical parameters are modelling assumptions, not wet-lab facts.

The environment owns private causal truth, public resources, assay behavior, candidate lineage, and terminal state. It implements reset(seed), available_actions(), step(action), agent_state(), is_terminal(), and score() without public truth access. Compound mechanisms are valid by construction.

World classes are SINGLE_FAILURE, COMPOUND_FAILURE, ASSAY_FAILURE, MODEL_FAILURE, and MIXED. The minimum cases are instability, aggregation plus kinetic defect, good molecule plus broken assay, good molecule plus invalid biological model, and a misleading-proxy/reward-hacking trap.

## Executable scenario registry

BinderBioPOMDP is the public implementation. reset(seed),
available_actions(), and step(action) return only AgentState, StepResult,
structured observations, candidate lineage, and resource state. The scenario
label is an environment-construction control and is never included in public
state or observations.

| Showcase scenario | Procedural world mode |
| --- | --- |
| instability | SINGLE_FAILURE |
| aggregation_kinetic_defect | COMPOUND_FAILURE |
| broken_assay | ASSAY_FAILURE |
