import { MetaBar } from './parts'

const LOOP = [
  ['Observe', 'Nineteen hourly undiluted OD600 readings arrive free of charge.'],
  ['Notice the ambiguity', 'A flat line is what a plateau looks like, and also what a saturated reader looks like.'],
  ['Design a control', 'Choose a retained aliquot, a dilution factor and a number of replicates.'],
  ['Measure', 'The virtual lab returns noisy replicate readings; each costs one of 6 units.'],
  ['Update', 'Multiply by the dilution factor and compare with the undiluted reading.'],
  ['Repeat or conclude', 'Up to 12 turns within the budget.'],
  ['Submit', 'A diagnosis, P(biomass above reading) and an optional late biomass estimate.'],
  ['Score', 'The deterministic evaluator audits every request against the hidden world.'],
]

export function Method() {
  return (
    <div className="doc">
      <MetaBar
        items={[
          ['Benchmark', 'MIRAGE-Bio · OD600 saturation'],
          ['Scenario', 'scenario-v1'],
          ['Prompt', 'prompt-v2'],
          ['Gate 0', 'frozen'],
        ]}
      />
      <div className="doc__wrap">
        <header className="doc__hero">
          <p className="kicker">Method</p>
          <h1>Does the agent notice that a saturated reading is ambiguous, and run the control?</h1>
          <p className="lead">
            MIRAGE-Bio is a deterministic virtual microbiology lab. Every episode hides one of two worlds behind the same kind of growth curve, and scores the evidence
            the agent gathered as well as its answer.
          </p>
        </header>

        <section className="doc__section">
          <h3>The scientific loop</h3>
          <table className="bk">
            <tbody>
              {LOOP.map(([h, t], i) => (
                <tr key={h}>
                  <td style={{ width: 40 }} className="mono faint">
                    {String(i + 1).padStart(2, '0')}
                  </td>
                  <td style={{ width: 220 }}>{h}</td>
                  <td className="why">{t}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section className="doc__section">
          <h3>Two hidden worlds</h3>
          <div className="hyp">
            <div>
              <code>BIOMASS_AS_READ</code>
              <b>Biological plateau.</b> The culture reaches its carrying capacity K below the reader's ceiling S. A diluted reading multiplied by its factor agrees with
              the undiluted reading.
            </div>
            <div>
              <code>BIOMASS_ABOVE_READING</code>
              <b>Reader saturation.</b> K lies several times above S. The undiluted readings flatten anyway; only a dilution reveals the true biomass.
            </div>
          </div>
        </section>

        <section className="doc__section doc__cols">
          <div>
            <h3>Latent growth (Richards)</h3>
            <div className="eq">dX/dt = r X [1 − (X/K)^ν]</div>
            <div className="eq">X(t)^−ν = K^−ν + (X₀^−ν − K^−ν) e^(−ν r t)</div>
            <p className="small">r, K, ν and X₀ are sampled per episode from the frozen scenario prior and never shown to the agent.</p>
          </div>
          <div>
            <h3>Saturating assay</h3>
            <div className="eq">f(x) = x [1 + (x/S)^n]^(−1/n)</div>
            <p className="small">Linear at low density and capped at S at high density; blank-subtracted, with relative and absolute noise and a 0.0001 resolution.</p>
          </div>
        </section>

        <section className="doc__section">
          <h3>What is scored</h3>
          <table className="bk">
            <thead>
              <tr>
                <th>Metric</th>
                <th className="l">Definition</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>M1 · Correct</td>
                <td className="why">The diagnosis matches the hidden condition.</td>
              </tr>
              <tr>
                <td>M2 · Diagnostic control</td>
                <td className="why">At least one late (12–18 h), diluted measurement in the frozen diagnostic action set, before the diagnosis.</td>
              </tr>
              <tr>
                <td>M3 · Correct and justified</td>
                <td className="why">M1 and M2 both hold. The headline: it catches right answers reached for the wrong reason.</td>
              </tr>
              <tr>
                <td>M4 · Cost</td>
                <td className="why">Measurement units spent, of 6.</td>
              </tr>
              <tr>
                <td>Q1 · Reconstruction</td>
                <td className="why">A diluted reading landed in the reader's useful region (descriptive; not part of M3).</td>
              </tr>
              <tr>
                <td>Brier</td>
                <td className="why">(p − y)² for the stated P(biomass above reading); lower is better calibrated.</td>
              </tr>
            </tbody>
          </table>
        </section>

        <section className="doc__section doc__cols">
          <div>
            <h3>Trust boundary</h3>
            <p className="small">
              The agent and the public Lab API see only readings, budget and their own events. The hidden condition, growth parameters and evaluator audit stay on the
              server and appear only after a diagnosis is scored, through a token-gated verdict route.
            </p>
          </div>
          <div>
            <h3>Validity (Gate 0)</h3>
            <p className="small">
              Before any agent ran, Gate 0 checked that passive curves are genuinely ambiguous and that a dilution control separates the two worlds. Its thresholds and
              the diagnostic action set are frozen.
            </p>
          </div>
        </section>

        <section className="doc__section">
          <h3>Limitations</h3>
          <p className="small">
            One controlled scenario with one assay failure mode, and 30 sampled episodes per agent: the results describe behaviour in MIRAGE-Bio, not general scientific
            ability. In plateau cultures the reader under-reads true biomass by about 2–4%; this is documented in <span className="mono">OPEN_RULINGS.md</span> and was
            not used to rescore anything.
          </p>
        </section>
      </div>
    </div>
  )
}
