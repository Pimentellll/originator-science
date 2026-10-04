# Recording the UI demo with OBS (about 3 minutes)

This is a click-by-click recording plan for the web app. Every number you say comes from a committed
file (see "Sources"). The "Do not say" list in [`script.md`](script.md) still applies.

## Before you record

1. From a clean `main` checkout, run `./mirage demo`. Wait for the line saying the dev benchmark
   is ready (about 30 s) so that **Tools → Benchmark lab** has data.
2. Open a **separate Chrome window** (no extensions, bookmarks bar hidden: `Ctrl+Shift+B`) at
   the Cockpit URL that `./mirage demo` prints (it ends in `?transport=live`).
3. Set the window to 1920×1080 and the zoom to 110–125 % (`Ctrl +`). Check that the Compare
   page shows every lane without horizontal scrolling at that zoom.
4. Click through every step once (a dry run). Results are deterministic, so the recording
   matches the dry run.
5. OBS:
   - Scene: one **Window Capture** source for that Chrome window, plus your mic.
   - Settings → Video: base and output resolution 1920×1080, 30 fps.
   - Settings → Output: Recording format `mkv`, so a crash doesn't lose the file. Remux to mp4 afterwards
     (File → Remux Recordings).
   - Audio: mic around −12 dB peak, with a Noise Suppression filter.
6. Record each section below as **its own clip** (Start/Stop Recording between sections). Also
   record one continuous backup take at the end.

## Sections

| # | Clip | Time | Page |
|---|---|---|---|
| 1 | The question | 0:00–0:25 | Overview |
| 2 | The headline result | 0:25–1:05 | Growth benchmark → Results |
| 3 | One episode | 1:05–1:35 | Results → saturated culture's record |
| 4 | A binder campaign | 1:35–2:30 | Binder campaign → Start → guided demo |
| 5 | Compare policies | 2:30–3:00 | Binder campaign → Compare policies |

### 1. The question (Overview)

**Click:** the **MIRAGE** logo or **Overview**. Scroll slowly to "Two cultures, one curve."

> MIRAGE asks whether an AI scientist can tell when its evidence isn't enough. A growth curve
> that flattens has two hidden explanations: the culture really stopped growing, or the plate
> reader saturated. The passive readings can't tell them apart. One diluted measurement can.

### 2. The headline result (Growth benchmark → Results)

**Click:** **Growth benchmark**. Hover Figure 1, then scroll to Table 1.

> Every agent sees the same flattened curve and has the same budget. Claude Opus ran the dilution
> control in 30 of 30 cultures and was correct *and* justified in 29. PassiveBayes never collects
> evidence: it gets 20 of 30 right by guessing, and 0 of them count as justified. That gap, being
> right versus knowing, is what the benchmark measures.

Optional extra line (GPT-6 Luna is **not shown in the UI**, so say it, don't point at it):

> We also ran GPT-6 Luna as an exploratory check. It ran the control 30 of 30 times too, with 24
> of 30 justified.

### 3. One episode (the saturated culture)

**Click:** under Figure 1, **Open the saturated culture's record**. Step through it.

> This is the live Claude demo run. The undiluted readings flatten at about 1.0 from hour 7.
> Claude dilutes the 18-hour sample 10× and 40×, and both corrected readings come back at about
> 3.9. Two dilutions four-fold apart agree, so the flat curve is the reader saturating. It answers
> "biomass above the reading" with probability 0.97. The reveal: the true biomass was 4.0.

### 4. A binder campaign (Binder campaign → Start)

**Click:** **Binder campaign** → **▶ START GUIDED DEMO**. The Cockpit opens on "Step 1 — Failure".
Click **NEXT ▶** nine times (the button moves slightly between steps). Pause on these steps:

| Step | On screen | Say |
|---|---|---|
| 2 | SEC: monomer fraction 0.19 | "Cheap test first: the protein is badly aggregated." |
| 4 | Redesign for solubility → binder-001 | "It repairs the molecule instead of discarding it." |
| 6 | After SPR, "Assay invalid 0.13 → 0.82" | "Now it suspects the assay itself, so it doesn't decide yet." |
| 8 | Validate assay: "Assay invalid 0.82 → 0.00" | "One cheap control rules the assay out." |
| 10 | **CORRECT + JUSTIFIED** | "Right, and justified by evidence it chose to collect." |

> A designed protein binder has failed, and the cause could be the molecule, the assay or the
> biology. MIRAGE checks aggregation first, redesigns, measures binding, and then, because it
> still doubts the assay, runs a control before rejecting. The verdict is correct *and* justified.

### 5. Compare policies

**Click:** **Compare policies**. The lanes play on their own; click **SHOW ALL** to jump to the end. Click one chip in each lane to show its
detail. Optionally click **SHOW CHARTS**.

> Same failure and seed, five strategies. All of them reach the right answer here. Only the Rescue
> Planner and the Fixed Pipeline are *justified*, and only the Rescue Planner gets there without
> damaging the SPR instrument. Greedy EIG and Lookahead are right but not justified, because they
> never ruled out the assay. PPO isn't shown as working, because we haven't trained one.

## If something goes wrong

- **A page says NOT RUN or ERROR:** stop the clip. Check **Tools → System check**, restart
  `./mirage demo` if needed, then re-record only that clip.
- **Benchmark lab is empty:** the dev benchmark is still generating. Wait about 30 s.
- **Wrong zoom on one clip:** re-record that clip; the others are unaffected.

## Sources

| Number | File |
|---|---|
| Opus 30/30 control, 29/30 justified; PassiveBayes 20/30 correct, 0/30 justified | `experiments/results/20261003-2323_claude_strong/results.md` |
| about 1.0 plateau, 3.95 / 3.91 corrected, p = 0.97, true 4.0 | `experiments/results/demo/20261004-0016_claude_demo/replay/demo-MA.txt` |
| GPT-6 Luna 30/30 control, 24/30 justified (exploratory) | `experiments/exploratory/cross-family/RESULT.md` |
| Binder seed-9 verdicts per policy (SEMANTICS_V2) | PR #82 description; reproduce with the live API |
