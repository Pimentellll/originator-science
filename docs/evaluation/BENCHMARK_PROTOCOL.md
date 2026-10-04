# Benchmark protocol

Evaluate policies on the same held-out, seeded procedural worlds. Record scenario version, code version, seeds, policy configuration, action trace, resource use, terminal decision, and public replay. Keep development and held-out seed sets separate.

The privileged evaluator reads truth separately from the policy trace. It reports correctness and justification separately, including compound recognition, invalid-assay/model detection, unnecessary redesign, and resource use. No model call is required to replay an episode.
