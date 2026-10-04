# MIRAGE architecture

MIRAGE is a framework containing multiple ScientificEnvironment implementations. The original growth benchmark and the Binder BioPOMDP share the active-identifiability thesis while retaining their own scientific models.

~~~mermaid
flowchart LR
  Cockpit[Scientific Cockpit] --> Controller[MIRAGE Controller]
  Controller --> Policy[Scientific Policy]
  Controller --> Belief[Particle Belief Engine]
  Belief --> Planner[Campaign Planner]
  Planner --> Env[ScientificEnvironment]
  Env --> Binder[Binder BioPOMDP]
  Env --> Growth[Growth regression benchmark]
  Env --> Provenance[Public event provenance]
  Provenance --> Belief
  Provenance --> Cockpit
  Evaluator[Privileged evaluator] -. separate access .-> Env
~~~

~~~mermaid
sequenceDiagram
  participant P as Policy
  participant B as Belief
  participant E as Environment
  participant R as Provenance
  P->>E: ScientificAction
  E->>E: private transition + assay noise
  E-->>R: public observation/resource update
  R-->>B: event
  B-->>P: BeliefSummary / state
  P->>E: terminal action or next experiment
~~~

## Package direction

New work belongs approximately in src/mirage/core, src/mirage/environments/binder, belief, policies, training, evaluation, and api. Do not rename working growth packages merely to match this direction. Shared manifests and root files are integration-owned.

## Invariants

- Truth is factorised and private; W1-W8 names are scenario templates only.
- All policy-visible state and replay are public-only.
- Every stochastic path is reproducible from a seed.
- Training reward and privileged scientific evaluation are separate.
- Policies receive one common public contract.
