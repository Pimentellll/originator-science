# Scenario generation

Procedural worlds are generated from an explicit seed and scenario class. SAME seed plus SAME public action sequence must reproduce public observations and transitions; different seeds provide variation. Policies compare on identical seed lists.

SINGLE_FAILURE samples one molecular defect. COMPOUND_FAILURE samples compatible multiple defects, including aggregation plus fast dissociation. ASSAY_FAILURE samples a sufficiently good molecule with invalid downstream assay. MODEL_FAILURE samples a good molecule and valid assay with invalid biological translation. MIXED samples the configured mixture.

Scenario labels are generation controls and reporting archetypes; they are never policy-visible hidden truth and never force a mutually exclusive causal model.
