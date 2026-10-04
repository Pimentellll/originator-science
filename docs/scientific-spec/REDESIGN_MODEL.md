# Redesign model

Redesign is a simulator-backed, synthetic transition, not a claim to predict real mutations. Each operation creates a new public Candidate with a new identifier, incremented generation, and parent identifier. The environment privately samples the new factorised state using a seeded transition.

REDESIGN_STABILITY has strong expected stability improvement and possible weak trade-offs. REDESIGN_SOLUBILITY has strong expected aggregation/developability improvement. REDESIGN_INTERFACE has expected affinity/kinetic improvement with a small possible stability/aggregation downside.

The interface must remain pluggable so future sequence/design engines can implement how proposals are generated while MIRAGE continues to decide what to improve and why.
