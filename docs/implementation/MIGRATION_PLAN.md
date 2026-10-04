# Migration plan

Status: **complete** as of `d182a2c`; kept as the record of the order used.

1. Preserved and kept testing the implemented growth benchmark (MIRAGE-Bio) as a regression target. Done.
2. Added core public contracts without moving v1 code. Done.
3. Added the Binder environment beside the existing packages with private truth and a public facade. Done.
4. Added belief and baseline policies against the public contract. Done.
5. Added privileged evaluation, event provenance, replay and API DTOs. Done.
6. Added training adapters and the frontend. Done (PPO unevaluated).
7. Integrated through the integration branch after contract tests and seed-compatibility checks. Done.

Do not rename packages or change shared manifests during feature work without integration ownership.
