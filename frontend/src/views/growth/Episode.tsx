import { useState } from "react";
import {
  Diamonds,
  Dots,
  HLine,
  Line,
  Plot,
} from "../../components/figures/Plot";
import { INK } from "../../components/figures/ink";
import {
  dilutionAgreement,
  downloadText,
  episodeReadingsCsv,
  foldOverUndiluted,
  hypothesisFor,
  outcome,
} from "../../lib/growth/analysis";
import type {
  GrowthEpisode,
  GrowthGrid,
  GrowthRun,
  Reading,
} from "../../lib/growth/types";
import type { Route } from "../../state/route";
import { CONDITION_LABEL, DIAG_LABEL, agentMeta, fmt, runMeta } from "./agents";
import { growthClient, useAsync } from "./data";
import { Check, DocState, MetaBar } from "./parts";

type Loaded = {
  ep: GrowthEpisode;
  run: GrowthRun;
  grid: GrowthGrid | null;
  passive: { runId: string; ep: GrowthEpisode } | null;
};

async function load(runId: string, episodeId: string): Promise<Loaded> {
  const c = growthClient();
  const [ep, run] = await Promise.all([
    c.getEpisode(runId, episodeId),
    c.getRun(runId),
  ]);
  let grid: GrowthGrid | null = null;
  let passive: Loaded["passive"] = null;
  if (run.run.matrix) {
    grid = await c.getGrid(run.run.matrix).catch(() => null);
    const pb = grid?.columns.find((col) => col.agent === "passive_bayes");
    if (
      pb &&
      pb.run_id !== runId &&
      grid?.rows.some((r) => r.episode_id === episodeId)
    ) {
      passive = await c.getEpisode(pb.run_id, episodeId).then(
        (e) => ({ runId: pb.run_id, ep: e }),
        () => null,
      );
    }
  }
  return { ep, run, grid, passive };
}

const STEPS = [
  "Question",
  "Passive evidence",
  "Ambiguity",
  "Experiment design",
  "Raw data",
  "Analysis",
  "Conclusion",
  "Evaluation",
  "Hidden truth",
  "Provenance",
  "Limitations",
];

export function Episode({
  params,
  navigate,
}: {
  params: string[];
  navigate: (r: Route, ...p: string[]) => void;
}) {
  const [runId, episodeId] = params;
  const data = useAsync(`${runId}/${episodeId}`, () =>
    runId && episodeId
      ? load(runId, episodeId)
      : Promise.reject(new Error("Choose an episode from the results grid.")),
  );
  const [revealedKey, setRevealedKey] = useState<string | null>(null);
  if (!runId || !episodeId)
    return (
      <div className="doc">
        <div className="doc__wrap doc__state">
          <p>
            An episode is one agent working on one culture. Pick one from the
            grid of every scored episode on the Results page.
          </p>
          <button
            className="btn btn--primary"
            onClick={() => navigate("results")}
          >
            Go to Results
          </button>
        </div>
      </div>
    );
  if (data.state !== "ready")
    return <DocState async={data} what={`episode ${episodeId ?? ""}`} />;
  const revealed = revealedKey === `${runId}/${episodeId}`;
  const { ep, run, grid, passive } = data.value;
  const meta = runMeta(run.run);
  const cfg = ep.episode;
  const ms = ep.derived.measurements;
  const measureEvents = ep.events.filter((e) => e.tool === "measure_od");
  const okMeasures = measureEvents.filter((e) => e.ok);
  const units = ep.scores.cost_units;
  const o = outcome({
    correct: ep.diagnosis ? ep.scores.correct : null,
    justified: ep.scores.justified,
    status: ep.status,
  });
  const agreement = dilutionAgreement(ms);
  const declared = ep.events.filter((e) => e.tool === "declare_state" && e.ok);
  const row = grid?.rows.find((r) => r.episode_id === episodeId);
  const S = cfg.assay.s_odeq;
  const K = cfg.growth.k_odeq;
  const ymax =
    Math.max(
      1,
      ...ep.passive.map((r) => r.mean_reading),
      ...ms.map((m) => m.back_corrected ?? 0),
      revealed ? K : 0,
    ) * 1.15;
  const yt = niceTicks(ymax);
  const go = (i: number) =>
    document
      .getElementById(`step-${i}`)
      ?.scrollIntoView({ behavior: "smooth" });

  return (
    <div className="doc">
      <MetaBar
        items={[
          ["Run", run.run.run_id],
          ["Agent", `${meta.code} ${meta.name}`],
          ["Seed", String(cfg.seed)],
          ["Scenario", cfg.scenario_version],
        ]}
      />
      <div className="doc__wrap">
        <div className="crumb">
          <button onClick={() => navigate("results")}>Results</button> /{" "}
          {run.run.matrix ?? "run"} / {episodeId}
        </div>
        <header className="ephead">
          <h1>
            {episodeId}: {outcomeTitle(o)}
          </h1>
          <div className="verdict">
            <span>
              Diagnosis
              <b>
                {ep.diagnosis
                  ? DIAG_LABEL[ep.diagnosis.diagnosis]
                  : "none submitted"}
              </b>
            </span>
            <span>
              P(above reading)
              <b>{fmt(ep.diagnosis?.p_biomass_above_reading, 2)}</b>
            </span>
            <span>
              Controls run<b>{okMeasures.length}</b>
            </span>
            <span>
              Units<b>{units} / 6</b>
            </span>
            <span>
              Brier<b>{fmt(ep.scores.brier, 4)}</b>
            </span>
            <span>
              Status<b>{ep.status.toLowerCase().replace("_", " ")}</b>
            </span>
          </div>
        </header>

        <div className="eplayout">
          <nav className="toc" aria-label="Steps">
            <ol>
              {STEPS.map((s, i) => (
                <li key={s}>
                  <button onClick={() => go(i)}>
                    <span className="n">{String(i + 1).padStart(2, "0")}</span>
                    {s}
                  </button>
                </li>
              ))}
            </ol>
          </nav>

          <div>
            <Step
              i={0}
              title="Is the biomass at the level the reader shows, or higher?"
            >
              <p>
                The agent receives an 18-hour batch culture and the question it
                is scored on: over the final hours, is biomass at the level the
                undiluted readings indicate, or higher?
              </p>
              <div className="hyp">
                <div>
                  <code>BIOMASS_AS_READ</code>
                  <span className="small">
                    H₀ · the culture really plateaued where the readings flatten
                    (biological plateau)
                  </span>
                </div>
                <div>
                  <code>BIOMASS_ABOVE_READING</code>
                  <span className="small">
                    H₁ · the reader saturated; true biomass is higher
                    (measurement artefact)
                  </span>
                </div>
              </div>
              <p className="small">
                The agent must also state P(H₁) and may estimate the late
                biomass in OD units.
              </p>
            </Step>

            <Step
              i={1}
              title={`${ep.passive.length} hourly readings of undiluted culture, free of charge.`}
            >
              <figure>
                <Plot
                  width={660}
                  height={310}
                  ymax={ymax}
                  yticks={yt}
                  right={122}
                  title="Episode growth curve"
                  ydigits={yt[1] < 1 ? 1 : 0}
                >
                  {(s) => (
                    <>
                      {revealed && <HLine s={s} y={S} stroke={INK.mute} />}
                      {revealed && (
                        <Line
                          s={s}
                          points={ep.derived.latent_curve}
                          stroke={INK.red}
                          dash="4 3"
                          width={1.3}
                        />
                      )}
                      {revealed && (
                        <Line
                          s={s}
                          points={ep.derived.reading_curve}
                          stroke={INK.ink2}
                          width={0.8}
                        />
                      )}
                      <Dots
                        s={s}
                        points={ep.passive.map((r) => [
                          r.time_h,
                          r.mean_reading,
                        ])}
                        fill={INK.ink}
                        r={3}
                        tip={([t, v]) => `${t} h, undiluted: ${v.toFixed(4)}`}
                      />
                      <Diamonds
                        s={s}
                        fill={INK.blue}
                        points={ms.flatMap((m, i) =>
                          m.time_h === null || m.back_corrected === null
                            ? []
                            : [
                                {
                                  t: m.time_h,
                                  v: m.back_corrected,
                                  key: String(i),
                                  dx: sameTimeIndex(ms, i),
                                  tip: `turn ${m.turn}: 1:${m.dilution_factor} at ${m.time_h} h → ${m.back_corrected.toFixed(3)}`,
                                },
                              ],
                        )}
                      />
                      <text
                        className="fig__lab"
                        x={s.x(18) + 10}
                        y={
                          s.y(
                            ep.passive[ep.passive.length - 1]?.mean_reading ??
                              0,
                          ) + 4
                        }
                        style={{ fill: INK.ink }}
                      >
                        undiluted
                      </text>
                      {ms.length > 0 && (
                        <text
                          className="fig__lab"
                          x={s.x(18) + 10}
                          y={
                            s.y(
                              Math.max(...ms.map((m) => m.back_corrected ?? 0)),
                            ) - 8
                          }
                          style={{ fill: INK.blue }}
                        >
                          diluted × factor
                        </text>
                      )}
                      {revealed && (
                        <>
                          <text
                            className="fig__lab"
                            x={s.x(18) + 10}
                            y={
                              s.y(K) +
                              (Math.abs(K - (ms[0]?.back_corrected ?? -9)) <
                              ymax * 0.06
                                ? 16
                                : 4)
                            }
                            style={{ fill: INK.red }}
                          >
                            true biomass
                          </text>
                          <text
                            className="fig__lab"
                            x={s.x(0.3)}
                            y={s.y(S) - 5}
                            style={{ fill: INK.mute }}
                          >
                            reader ceiling S = {S.toFixed(2)}
                          </text>
                        </>
                      )}
                    </>
                  )}
                </Plot>
                <figcaption>
                  <b>Figure. Readings for this culture.</b> Dots: undiluted
                  passive readings. Diamonds: the agent's diluted readings
                  multiplied by their dilution factor.
                  {revealed
                    ? " Dashed red: hidden true biomass; thin line: noise-free reader response; dotted: reader ceiling."
                    : " The true biomass and reader ceiling are hidden until step 09."}
                </figcaption>
              </figure>
              <PassiveTable passive={ep.passive} />
            </Step>

            <Step i={2} title="Why the curve alone cannot decide.">
              <p>
                A curve that rises and then stops abruptly is what stationary
                phase looks like, and also what a reader at its ceiling looks
                like. Undiluted readings cannot exceed the ceiling, so more
                undiluted readings, at any time, cannot separate the two
                hypotheses.
              </p>
              {passive?.ep.diagnosis && (
                <p className="small">
                  PassiveBayes integrates over the scenario prior using only
                  these passive readings. For this culture it states P(H₁) ={" "}
                  <b>
                    {passive.ep.diagnosis.p_biomass_above_reading.toFixed(3)}
                  </b>
                  {Math.abs(
                    passive.ep.diagnosis.p_biomass_above_reading - 0.5,
                  ) < 0.15
                    ? ", close to a coin flip."
                    : "."}
                </p>
              )}
              <p className="small">
                A dilution brings the aliquot back into the reader's linear
                range. If the culture plateaued, reading × factor matches the
                undiluted value; if the reader saturated, it is several times
                higher.
              </p>
            </Step>

            <Step i={3} title="What the agent chose to measure.">
              {measureEvents.length === 0 ? (
                <p>
                  <b>No measurements.</b> The agent diagnosed from the passive
                  curve alone.
                </p>
              ) : (
                <table className="bk dense">
                  <thead>
                    <tr>
                      <th>Turn</th>
                      <th>Aliquot</th>
                      <th>Dilution</th>
                      <th>Replicates</th>
                      <th>Cost</th>
                      <th className="l">Instrument</th>
                    </tr>
                  </thead>
                  <tbody>
                    {measureEvents.map((e) => (
                      <tr key={e.index}>
                        <td>{e.turn}</td>
                        <td>{String(e.arguments.time_h)} h</td>
                        <td>1:{String(e.arguments.dilution_factor ?? 1)}</td>
                        <td>{String(e.arguments.replicates ?? 1)}</td>
                        <td>
                          {e.ok ? String(e.arguments.replicates ?? 1) : 0}
                        </td>
                        <td className="why">
                          {e.ok
                            ? "returned readings"
                            : `rejected: ${e.error ?? "error"}`}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              {declared.length > 0 && (
                <>
                  <h3 style={{ marginTop: 18 }}>Declared working state</h3>
                  <table className="bk dense">
                    <tbody>
                      {declared.map((e) => (
                        <tr key={e.index}>
                          <td style={{ width: 60 }}>turn {e.turn}</td>
                          <td style={{ width: 90 }}>
                            P ={" "}
                            {fmt(
                              e.arguments.p_biomass_above_reading as
                                number | null,
                              2,
                            )}
                          </td>
                          <td className="why">
                            {String(e.arguments.notes ?? "")}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </>
              )}
              <p className="small" style={{ marginTop: 12 }}>
                Budget: 1 unit per replicate reading, 6 units in total; {units}{" "}
                spent. Passive readings are free.
              </p>
            </Step>

            <Step
              i={4}
              title="Replicate readings exactly as returned by the instrument."
            >
              {okMeasures.length === 0 ? (
                <p className="small">No diluted readings were taken.</p>
              ) : (
                <table className="bk dense">
                  <thead>
                    <tr>
                      <th>Turn</th>
                      <th>Aliquot</th>
                      <th>Dilution</th>
                      {Array.from(
                        {
                          length: Math.max(
                            ...okMeasures.map(
                              (e) =>
                                ((e.result?.readings as number[]) ?? []).length,
                            ),
                          ),
                        },
                        (_, i) => (
                          <th key={i}>Rep. {i + 1}</th>
                        ),
                      )}
                      <th>Mean</th>
                    </tr>
                  </thead>
                  <tbody>
                    {okMeasures.map((e) => {
                      const r = e.result as {
                        readings: number[];
                        mean_reading: number;
                        time_h: number;
                        dilution_factor: number;
                      };
                      const width = Math.max(
                        ...okMeasures.map(
                          (x) =>
                            ((x.result?.readings as number[]) ?? []).length,
                        ),
                      );
                      return (
                        <tr key={e.index}>
                          <td>{e.turn}</td>
                          <td>{r.time_h} h</td>
                          <td>1:{r.dilution_factor}</td>
                          {Array.from({ length: width }, (_, i) => (
                            <td key={i} className="mono">
                              {r.readings[i] === undefined
                                ? ""
                                : r.readings[i].toFixed(4)}
                            </td>
                          ))}
                          <td className="mono">{r.mean_reading.toFixed(4)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
              <p className="small" style={{ marginTop: 10 }}>
                OD600, blank-subtracted, resolution 0.0001.{" "}
                <ExportLinks ep={ep} runId={runId} />
              </p>
            </Step>

            <Step
              i={5}
              title="Correct for dilution and compare with the undiluted reading."
            >
              {ms.length === 0 ? (
                <p className="small">
                  Nothing to correct: the diagnosis rests on the undiluted curve
                  alone.
                </p>
              ) : (
                <table className="bk dense">
                  <thead>
                    <tr>
                      <th>Aliquot</th>
                      <th>Mean × dilution</th>
                      <th>Undiluted reading</th>
                      <th>Ratio</th>
                    </tr>
                  </thead>
                  <tbody>
                    {ms.map((m) => {
                      const f = foldOverUndiluted(m, ep.passive);
                      const u = ep.passive.find(
                        (r) => r.time_h === m.time_h,
                      )?.mean_reading;
                      return (
                        <tr key={m.event_index}>
                          <td>
                            {m.time_h} h, 1:{m.dilution_factor}
                          </td>
                          <td className="mono">
                            {fmt(m.mean_reading, 4)} × {m.dilution_factor} ={" "}
                            <b>{fmt(m.back_corrected, 3)}</b>
                          </td>
                          <td className="mono">{fmt(u, 4)}</td>
                          <td>{f === null ? "—" : `${f.toFixed(2)}×`}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
              {agreement.map((a) => (
                <p key={a.time_h} className="small" style={{ marginTop: 12 }}>
                  At {a.time_h} h, dilutions{" "}
                  {a.factors.map((f) => `1:${f}`).join(" and ")} give{" "}
                  {a.values.map((v) => v.toFixed(3)).join(" and ")} after
                  correction: a relative spread of{" "}
                  {(a.relSpread * 100).toFixed(1)}%.{" "}
                  {a.relSpread < 0.1
                    ? "They agree, so both reads are in the proportional range."
                    : "They disagree, so at least one read is outside the proportional range."}
                </p>
              ))}
              {ms.length > 0 && agreement.length === 0 && (
                <p className="small" style={{ marginTop: 12 }}>
                  No time point was read at two dilution factors, so linearity
                  was not checked directly.
                </p>
              )}
            </Step>

            <Step i={6} title="The agent's submitted diagnosis.">
              {ep.diagnosis ? (
                <>
                  <dl className="kv">
                    <dt>Diagnosis</dt>
                    <dd>
                      <code>{ep.diagnosis.diagnosis}</code>
                    </dd>
                    <dt>P(above reading)</dt>
                    <dd>{ep.diagnosis.p_biomass_above_reading.toFixed(2)}</dd>
                    <dt>Late biomass</dt>
                    <dd>
                      {ep.diagnosis.late_biomass_estimate_od === null
                        ? "not estimated"
                        : `≈ ${ep.diagnosis.late_biomass_estimate_od} OD`}
                    </dd>
                  </dl>
                  <p className="quote" style={{ marginTop: 14 }}>
                    “{ep.diagnosis.rationale}”
                  </p>
                </>
              ) : (
                <p>No diagnosis was submitted (status {ep.status}).</p>
              )}
            </Step>

            <Step i={7} title="What the deterministic evaluator checked.">
              <table className="bk checks">
                <tbody>
                  <tr>
                    <td>M1 · Correct diagnosis</td>
                    <td className="why">matches the hidden condition</td>
                    <td>
                      <Check ok={ep.diagnosis ? ep.scores.correct : null} />
                    </td>
                  </tr>
                  <tr>
                    <td>M2 · Diagnostic control</td>
                    <td className="why">
                      {ep.audit.filter((a) => a.diagnostic_control).length} of{" "}
                      {ep.audit.length} requests late, diluted, in the
                      diagnostic set and before diagnosis
                    </td>
                    <td>
                      <Check ok={ep.scores.diagnostic_control} />
                    </td>
                  </tr>
                  <tr>
                    <td>M3 · Correct and justified</td>
                    <td className="why">M1 and M2 both hold</td>
                    <td>
                      <Check ok={ep.diagnosis ? ep.scores.justified : null} />
                    </td>
                  </tr>
                  <tr>
                    <td>Q1 · Reconstruction</td>
                    <td className="why">
                      a diluted read in the reader's useful region
                    </td>
                    <td>
                      <Check ok={ep.scores.reconstruction_adequate} />
                    </td>
                  </tr>
                  <tr>
                    <td>Calibration</td>
                    <td className="why">Brier (p − y)²</td>
                    <td className="mono">{fmt(ep.scores.brier, 4)}</td>
                  </tr>
                  <tr>
                    <td>M4 · Cost</td>
                    <td className="why">units spent</td>
                    <td className="mono">{units} / 6</td>
                  </tr>
                </tbody>
              </table>
              {ep.audit.length > 0 && (
                <>
                  <h3 style={{ marginTop: 20 }}>Per-request audit</h3>
                  <table className="bk dense">
                    <thead>
                      <tr>
                        <th>Request</th>
                        <th>Late</th>
                        <th>Diluted</th>
                        <th>In set</th>
                        <th>Before dx</th>
                        <th>Useful region</th>
                        <th>Control</th>
                      </tr>
                    </thead>
                    <tbody>
                      {ep.audit.map((a) => (
                        <tr key={a.event_index}>
                          <td>#{a.request_index + 1}</td>
                          <td>{yn(a.is_late)}</td>
                          <td>{yn(a.is_diluted)}</td>
                          <td>{yn(a.in_diagnostic_set)}</td>
                          <td>{yn(a.before_diagnosis)}</td>
                          <td>{yn(a.in_useful_region)}</td>
                          <td>
                            <Check ok={a.diagnostic_control} />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </>
              )}
            </Step>

            <Step i={8} title="Revealed only after the diagnosis is scored.">
              {!revealed ? (
                <button
                  className="pbtn"
                  onClick={() => setRevealedKey(`${runId}/${episodeId}`)}
                >
                  Reveal the hidden world
                </button>
              ) : (
                <div className="truthbox">
                  <span className="sc">
                    Evaluator-only · not visible to the agent
                  </span>
                  <dl className="kv" style={{ marginTop: 8 }}>
                    <dt>Condition</dt>
                    <dd>
                      {CONDITION_LABEL[cfg.condition]} (expects{" "}
                      <code>{hypothesisFor(cfg.condition)}</code>)
                    </dd>
                    <dt>True biomass K</dt>
                    <dd>{K.toFixed(3)} OD</dd>
                    <dt>Reader ceiling S</dt>
                    <dd>{S.toFixed(3)} OD</dd>
                    <dt>K / S</dt>
                    <dd>{cfg.k_ratio.toFixed(2)}</dd>
                    <dt>Growth</dt>
                    <dd className="mono">
                      r = {cfg.growth.r_per_h.toFixed(3)} h⁻¹ · ν ={" "}
                      {cfg.growth.nu} · X₀ = {cfg.growth.x0_odeq.toFixed(4)}
                    </dd>
                    <dt>Estimate error</dt>
                    <dd>
                      {ep.diagnosis?.late_biomass_estimate_od == null
                        ? "—"
                        : `${((ep.diagnosis.late_biomass_estimate_od / K - 1) * 100).toFixed(1)}%`}
                    </dd>
                    {ep.audit.length > 0 && (
                      <>
                        <dt>Presented to reader</dt>
                        <dd className="mono">
                          {ep.audit
                            .map((a) => a.presented_biomass_odeq.toFixed(3))
                            .join(", ")}{" "}
                          OD
                        </dd>
                      </>
                    )}
                  </dl>
                  <p className="small" style={{ marginTop: 10 }}>
                    The figure in step 02 now shows the true biomass and the
                    reader ceiling.
                  </p>
                </div>
              )}
            </Step>

            <Step i={9} title="Everything needed to reproduce this page.">
              <dl className="kv">
                <dt>Run</dt>
                <dd className="mono">{run.run.run_id}</dd>
                <dt>Agent</dt>
                <dd>
                  {ep.agent.model ?? ep.agent.name}
                  {ep.agent.effort ? ` · effort ${ep.agent.effort}` : ""}
                  {ep.agent.prompt_version
                    ? ` · ${ep.agent.prompt_version}`
                    : ""}{" "}
                  {ep.agent.prompt_sha256 && (
                    <span className="mono">
                      {ep.agent.prompt_sha256.slice(0, 12)}…
                    </span>
                  )}
                </dd>
                <dt>Scenario</dt>
                <dd>
                  {cfg.scenario_version}{" "}
                  <span className="mono">
                    {cfg.scenario_sha256.slice(0, 12)}…
                  </span>{" "}
                  · seed {cfg.seed}
                </dd>
                <dt>Software</dt>
                <dd>
                  {Object.entries(ep.versions)
                    .map(([k, v]) => `${k} ${v}`)
                    .join(" · ")}
                </dd>
                <dt>Recorded</dt>
                <dd className="mono">
                  {String(ep.run_meta.started_at ?? "—")}
                </dd>
                <dt>Schema</dt>
                <dd className="mono">{ep.schema_version}</dd>
                <dt>Frozen</dt>
                <dd>{run.run.frozen ? "yes · SHA-256 in FREEZE.md" : "no"}</dd>
              </dl>
              <pre>{`python -m mirage.demo.replay \\\n  experiments/results/${run.run.run_id}/episodes/${episodeId}.json --pace 0`}</pre>
              <p className="small" style={{ marginTop: 10 }}>
                <ExportLinks ep={ep} runId={runId} />
              </p>
            </Step>

            <Step i={10} title="What this episode does not show.">
              <p className="small">
                A synthetic culture with one assay failure mode; growth follows
                a Richards model and the reader a fixed saturation curve. This
                is one episode of {run.run.n_episodes}. The reader also
                under-reads plateau cultures by 2–4%, the cause of both Claude
                models' single miss (<span className="mono">s500028-BP</span>).
              </p>
            </Step>
          </div>

          <aside className="side">
            {row && grid && (
              <div className="note">
                <span className="sc">Same culture, every agent</span>
                <div className="cmpbox">
                  {grid.columns.map((c) => {
                    const cell = row.cells[c.run_id];
                    const m = agentMeta(c.agent, c.model);
                    const oc = cell ? outcome(cell) : "none";
                    return (
                      <div className="row" key={c.run_id}>
                        {c.run_id === runId ? (
                          <b>
                            {m.code} {m.name}
                          </b>
                        ) : (
                          <button
                            className="crumb-link"
                            onClick={() =>
                              navigate("episode", c.run_id, episodeId)
                            }
                          >
                            {m.code} {m.name}
                          </button>
                        )}
                        <span
                          className={
                            oc === "justified"
                              ? "pass"
                              : oc === "none"
                                ? "na"
                                : "fail"
                          }
                        >
                          {OUTCOME_SHORT[oc]}
                        </span>
                      </div>
                    );
                  })}
                </div>
                {passive?.ep.diagnosis &&
                  passive.ep.scores.correct &&
                  !passive.ep.scores.justified && (
                    <p style={{ margin: "8px 0 0" }}>
                      PassiveBayes gets this one right with P ={" "}
                      {passive.ep.diagnosis.p_biomass_above_reading.toFixed(3)}{" "}
                      and no measurement. Accuracy cannot tell it apart from an
                      agent that checked; M3 can.
                    </p>
                  )}
              </div>
            )}
            <div className="note">
              <span className="sc">Dilution arithmetic</span>A reading taken at
              1:<i>f</i> is multiplied by <i>f</i>. If the corrected values at
              two factors agree, both reads are in the linear range.
            </div>
            <div className="note">
              <span className="sc">Budget</span>1 unit per replicate reading, 6
              units in total, up to 12 turns. Passive readings are free.
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
}

const OUTCOME_SHORT = {
  justified: "justified",
  unjustified: "unjustified",
  wrong: "wrong",
  none: "no dx",
} as const;

function outcomeTitle(o: "justified" | "unjustified" | "wrong" | "none") {
  return {
    justified: "correct, and justified by a control",
    unjustified: "correct, but not justified",
    wrong: "wrong diagnosis",
    none: "no diagnosis",
  }[o];
}

function yn(v: boolean) {
  return v ? "yes" : <span className="fail">no</span>;
}

function sameTimeIndex(ms: { time_h: number | null }[], i: number) {
  return ms.slice(0, i).filter((m) => m.time_h === ms[i].time_h).length;
}

function niceTicks(max: number) {
  const step = max <= 1.5 ? 0.25 : max <= 3.5 ? 0.5 : 1;
  return Array.from(
    { length: Math.floor(max / step) + 1 },
    (_, i) => +(i * step).toFixed(2),
  );
}

function Step({
  i,
  title,
  children,
}: {
  i: number;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="step" id={`step-${i}`}>
      <div className="step__n">
        Step {String(i + 1).padStart(2, "0")} · {STEPS[i]}
      </div>
      <h2>{title}</h2>
      {children}
    </section>
  );
}

function PassiveTable({ passive }: { passive: Reading[] }) {
  const rows: Reading[][] = [];
  for (let i = 0; i < passive.length; i += 7)
    rows.push(passive.slice(i, i + 7));
  return (
    <div style={{ marginTop: 14 }}>
      {rows.map((chunk) => (
        <table
          key={chunk[0].time_h}
          className="bk dense"
          style={{ fontSize: 13, marginBottom: 10 }}
        >
          <tbody>
            <tr>
              <td className="sc">t (h)</td>
              {chunk.map((r) => (
                <td key={r.time_h} className="mono">
                  {r.time_h}
                </td>
              ))}
            </tr>
            <tr>
              <td className="sc">OD600</td>
              {chunk.map((r) => (
                <td key={r.time_h} className="mono">
                  {r.mean_reading.toFixed(3)}
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      ))}
    </div>
  );
}

function ExportLinks({ ep, runId }: { ep: GrowthEpisode; runId: string }) {
  const id = ep.episode.episode_id;
  return (
    <span className="dlbar" style={{ display: "inline-flex" }}>
      <button
        onClick={() =>
          downloadText(
            `${runId}_${id}_readings.csv`,
            episodeReadingsCsv(ep),
            "text/csv",
          )
        }
      >
        Readings as CSV
      </button>
      <button
        onClick={() =>
          downloadText(
            `${runId}_${id}.json`,
            JSON.stringify(ep, null, 2),
            "application/json",
          )
        }
      >
        Episode record as JSON
      </button>
    </span>
  );
}
