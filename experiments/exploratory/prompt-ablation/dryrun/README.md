# Dry run (development seeds 0 and 1): pipeline check only

These four episodes (seeds 0 and 1, `dev2` matrix in `../dev_matrix.json`) were run before the
strong-matrix runs to check the driver end to end (REGISTRATION §4, step 1). They are **never
reported as results**. They are committed only so the session spend in `usage.jsonl` can be audited
(10 API calls, 26,530 input + 2,993 output tokens, ≈ $0.083). No bug was found; the driver and
prompts were not changed after the dry run.
