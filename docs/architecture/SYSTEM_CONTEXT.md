# System context

MIRAGE supports a scientist or policy choosing experiments within a simulated laboratory, then making an evidence-bounded terminal decision. The environment owns truth, resources, assay models, redesign transitions, and seeded randomness. The controller records public events; the belief engine consumes those events; the frontend renders only the public record.

~~~mermaid
flowchart TB
  User[Scientist or automated policy] --> API[Controller / public API]
  API --> Env[ScientificEnvironment]
  Env --> Obs[ScientificObservation]
  Obs --> Log[Public provenance]
  Log --> Belief[Belief summary]
  Log --> UI[Scientific Cockpit]
  Env -. evaluator-only .-> Eval[Scientific evaluator]
~~~

The original GrowthPlateau environment remains an implemented regression benchmark. BinderBioPOMDP is the primary in-development environment. An EGFR-inspired display is a narrative showcase, never evidence that synthetic benchmark binders are therapeutic or experimentally validated.
