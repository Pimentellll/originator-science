"""Replay saved MIRAGE-Bio episodes without a network or live model."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np

from mirage.biology.growth import richards
from mirage.config import EpisodeConfig
from mirage.evaluation.metrics import EpisodeResult

SECTIONS: tuple[str, ...] = (
    "== 1. Passive readings ==",
    "== 2. Agent notes (declare_state) ==",
    "== 3. Measurements (measure_od) ==",
    "== 4. Diagnosis ==",
    "== 5. REVEAL ==",
)
_SPARKLINE = "▁▂▃▄▅▆▇█"


def load_record(path: str | Path) -> EpisodeResult:
    return EpisodeResult.model_validate_json(Path(path).read_text(encoding="utf-8"))


def latent_curve(episode: EpisodeConfig, t_h) -> np.ndarray:
    growth = episode.growth
    return richards(
        t_h,
        k_odeq=growth.k_odeq,
        r_per_h=growth.r_per_h,
        x0_odeq=growth.x0_odeq,
        nu=growth.nu,
    )


def _nonnegative_float(value: str) -> float:
    try:
        pace = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("pace must be a number") from exc
    if pace < 0:
        raise argparse.ArgumentTypeError("pace must be at least 0")
    return pace


def _pause(pace: float) -> None:
    if pace > 0:
        time.sleep(pace)


def _print_passive(record: EpisodeResult) -> None:
    print(SECTIONS[0])
    print("time_h | mean_reading")
    for measurement in record.passive:
        print(f"{measurement.time_h:>6} | {measurement.mean_reading:.4f}")
    means = [measurement.mean_reading for measurement in record.passive]
    if means:
        low, high = min(means), max(means)
        span = high - low
        sparkline = "".join(
            _SPARKLINE[round((value - low) / span * (len(_SPARKLINE) - 1))]
            if span
            else _SPARKLINE[0]
            for value in means
        )
        print(sparkline)


def _print_agent_notes(record: EpisodeResult) -> None:
    print(SECTIONS[1])
    declarations = [
        event for event in record.events if event.tool == "declare_state" and event.ok
    ]
    if not declarations:
        print("(declare_state not called)")
        return
    for event in declarations:
        print(
            f"turn={event.turn} p_growth_continued="
            f"{event.arguments['p_growth_continued']} notes={event.arguments['notes']}"
        )


def _print_measurements(record: EpisodeResult, pace: float) -> None:
    print(SECTIONS[2])
    measurements = [event for event in record.events if event.tool == "measure_od"]
    if not measurements:
        print("(no measure_od calls)")
        return
    for index, event in enumerate(measurements):
        arguments = event.arguments
        line = (
            f"turn={event.turn} time_h={arguments['time_h']} "
            f"dilution_factor={arguments['dilution_factor']} "
            f"replicates={arguments['replicates']}"
        )
        if event.ok:
            result = event.result
            readings = ", ".join(f"{reading:.4f}" for reading in result["readings"])
            back_corrected = result["mean_reading"] * result["dilution_factor"]
            print(
                f"{line} readings=[{readings}] "
                f"mean_reading={result['mean_reading']:.4f} "
                f"budget_remaining={result['budget_remaining']} "
                f"back-corrected={back_corrected:.4f}"
            )
        else:
            print(f"{line} REJECTED (no charge): {event.error}")
        if index < len(measurements) - 1:
            _pause(pace)


def _print_diagnosis(record: EpisodeResult) -> None:
    print(SECTIONS[3])
    print(f"status={record.status}")
    diagnosis = record.diagnosis
    if diagnosis is None:
        print("no diagnosis")
        return
    rationale = diagnosis.rationale
    excerpt = rationale[:300] + ("…" if len(rationale) > 300 else "")
    print(f"diagnosis={diagnosis.diagnosis}")
    print(f"p_growth_continued={diagnosis.p_growth_continued}")
    print(f"late_biomass_estimate_od={diagnosis.late_biomass_estimate_od}")
    print(f"rationale={excerpt}")


def _print_reveal(record: EpisodeResult) -> None:
    print(SECTIONS[4])
    episode = record.episode
    print(
        f"condition={episode.condition.value} "
        f"K={episode.growth.k_odeq:.4f} S={episode.assay.s_odeq:.4f}"
    )
    events = {event.index: event for event in record.events}
    for audit in record.audit:
        event = events[audit.event_index]
        result = event.result
        back_corrected = result["mean_reading"] * result["dilution_factor"]
        print(
            f"event_index={audit.event_index} time_h={event.arguments['time_h']} "
            f"dilution={event.arguments['dilution_factor']} "
            f"back-corrected={back_corrected:.4f} "
            f"true_biomass={audit.latent_biomass_odeq:.4f} "
            f"is_late={audit.is_late} is_diluted={audit.is_diluted} "
            f"in_diagnostic_set={audit.in_diagnostic_set} "
            f"M2 diagnostic_control={audit.diagnostic_control} "
            f"in_useful_region={audit.in_useful_region} "
            f"Q1 reconstruction_adequate={audit.reconstruction_adequate}"
        )
    for name, value in record.scores.model_dump().items():
        print(f"{name}={value!r}")


def _write_figure(record: EpisodeResult, path: str | Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots()
    try:
        passive_times = [measurement.time_h for measurement in record.passive]
        passive_means = [measurement.mean_reading for measurement in record.passive]
        axes.scatter(passive_times, passive_means, marker="o", label="Passive readings")

        measurement_label_added = False
        for event in record.events:
            if event.tool != "measure_od" or not event.ok:
                continue
            result = event.result
            time_h = event.arguments["time_h"]
            dilution_factor = result["dilution_factor"]
            back_corrected = result["mean_reading"] * dilution_factor
            axes.scatter(
                [time_h],
                [back_corrected],
                marker="D",
                label="measure_od mean" if not measurement_label_added else None,
            )
            corrected_replicates = [
                reading * dilution_factor for reading in result["readings"]
            ]
            axes.scatter(
                [time_h] * len(corrected_replicates),
                corrected_replicates,
                marker="x",
                s=20,
                label="measure_od replicates" if not measurement_label_added else None,
            )
            measurement_label_added = True

        max_time = max(passive_times, default=0)
        times = np.linspace(0, max_time, 400)
        axes.plot(times, latent_curve(record.episode, times), "--", label="Latent X(t)")
        axes.set_xlabel("Time (h)")
        axes.set_ylabel("OD600 / biomass (ODeq)")
        axes.set_title(record.episode.episode_id)
        axes.legend()
        figure.savefig(path)
    finally:
        plt.close(figure)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("episode", type=Path)
    parser.add_argument("--pace", type=_nonnegative_float, default=1.0, metavar="SECONDS")
    parser.add_argument("--figure", type=Path)
    arguments = parser.parse_args(argv)

    record = load_record(arguments.episode)
    _print_passive(record)
    _pause(arguments.pace)
    _print_agent_notes(record)
    _pause(arguments.pace)
    _print_measurements(record, arguments.pace)
    _pause(arguments.pace)
    _print_diagnosis(record)
    _pause(arguments.pace)
    _print_reveal(record)
    if arguments.figure is not None:
        _write_figure(record, arguments.figure)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
