# Migration plan

1. Preserve and continuously test the implemented growth benchmark.
2. Add core public contracts without moving v1 code.
3. Add the Binder environment beside existing packages with private truth and public facade.
4. Add belief and baseline policies against the public contract.
5. Add privileged evaluation, event provenance, replay, and API DTOs.
6. Add training adapters and frontend.
7. Integrate through the integration branch after contract tests and seed compatibility checks.

Do not rename packages or change shared manifests during feature work without integration ownership.
