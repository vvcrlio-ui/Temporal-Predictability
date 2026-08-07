from __future__ import annotations

from collections import Counter

import numpy as np
import pandas as pd
import pytest

from analysis.learning_curve import (
    aggregate_median_errors,
    bootstrap_asymptote_intervals,
    fit_learning_curves,
    monotonize_nonincreasing,
    normalize_asymptotes,
    _resample_units,
)


def power_records(
    *,
    asymptote: float,
    scale: float,
    rate: float,
    sample_sizes: np.ndarray,
    unit_count: int = 1,
    noise_scale: float = 0.0,
    random_seed: int = 0,
) -> pd.DataFrame:
    rng = np.random.default_rng(random_seed)
    rows = []
    for unit in range(unit_count):
        for n_value in sample_sizes:
            noise = rng.normal(0.0, noise_scale) if noise_scale else 0.0
            rows.append(
                {
                    "unit": unit,
                    "N": float(n_value),
                    "metric": asymptote + scale * n_value ** (-rate) + noise,
                }
            )
    return pd.DataFrame(rows)


@pytest.mark.parametrize(
    ("asymptote", "scale", "rate", "sample_sizes"),
    [
        (0.08, 1.5, 0.7, np.geomspace(10, 640, 9)),
        (0.25, 3.2, 1.1, np.geomspace(5, 1_280, 11)),
        (0.45, 0.9, 0.4, np.geomspace(12, 768, 10)),
    ],
)
def test_power_fit_recovers_known_asymptote(
    asymptote: float, scale: float, rate: float, sample_sizes: np.ndarray
) -> None:
    result = fit_learning_curves(
        power_records(
            asymptote=asymptote,
            scale=scale,
            rate=rate,
            sample_sizes=sample_sizes,
        ),
        error_column="metric",
        forms=("power",),
    )

    estimate = result.fits.loc[0, "asymptote"]
    assert estimate == pytest.approx(asymptote, rel=1e-4)


@pytest.mark.parametrize(
    ("repeat_count", "bootstrap_iterations", "confidence_level"),
    [(40, 48, 0.9)],
)
def test_bootstrap_intervals_achieve_nominal_coverage(
    repeat_count: int, bootstrap_iterations: int, confidence_level: float
) -> None:
    asymptote = 0.2
    covered = []
    widths = []
    for repetition in range(repeat_count):
        intervals = bootstrap_asymptote_intervals(
            power_records(
                asymptote=asymptote,
                scale=1.8,
                rate=0.75,
                sample_sizes=np.geomspace(10, 640, 8),
                unit_count=31,
                noise_scale=0.025,
                random_seed=100 + repetition,
            ),
            sample_column="unit",
            error_column="metric",
            forms=("power",),
            iterations=bootstrap_iterations,
            confidence_level=confidence_level,
            random_seed=1_000 + repetition,
        )
        interval = intervals.iloc[0]
        covered.append(
            interval["asymptote_lower"] <= asymptote <= interval["asymptote_upper"]
        )
        widths.append(interval["asymptote_upper"] - interval["asymptote_lower"])

    observed_coverage = float(np.mean(covered))
    binomial_standard_error = np.sqrt(
        confidence_level * (1.0 - confidence_level) / repeat_count
    )
    assert abs(observed_coverage - confidence_level) <= 3 * binomial_standard_error
    assert float(np.mean(widths)) > 0


@pytest.mark.parametrize("unit_count", [4, 7])
def test_bootstrap_resampling_preserves_shared_unit_multiset(unit_count: int) -> None:
    rows = []
    for candidate in ("first", "second"):
        for unit in range(unit_count):
            for n_value in (10.0, 20.0):
                rows.append(
                    {
                        "collection": "synthetic",
                        "candidate": candidate,
                        "unit": unit,
                        "N": n_value,
                        "metric": 0.8 - 0.01 * unit,
                    }
                )
    resampled = _resample_units(
        pd.DataFrame(rows),
        sample_column="unit",
        group_columns=("collection", "candidate"),
        rng=np.random.default_rng(23),
    )
    unit_multisets = [
        Counter(subset["unit"])
        for _, subset in resampled.groupby("candidate", sort=True)
    ]
    assert len(unit_multisets) == 2
    assert unit_multisets[0] == unit_multisets[1]


@pytest.mark.parametrize("sample_sizes", [np.arange(1, 10), np.geomspace(2, 256, 10)])
def test_extrapolation_check_detects_mismatched_form(sample_sizes: np.ndarray) -> None:
    true_asymptote = 0.18
    true_scale = 1.1
    true_rate = 0.09
    frame = pd.DataFrame(
        {
            "N": sample_sizes.astype(float),
            "metric": true_asymptote + true_scale * np.exp(-true_rate * sample_sizes),
        }
    )
    matching_fit = fit_learning_curves(
        frame,
        error_column="metric",
        forms=("exponential",),
        extrapolation_cutoff=float(sample_sizes[-3]),
    ).fits.loc[0]
    mismatched_fit = fit_learning_curves(
        frame,
        error_column="metric",
        forms=("power",),
        extrapolation_cutoff=float(sample_sizes[-3]),
    ).fits.loc[0]

    assert matching_fit["extrapolation_check_status"] == "ok"
    assert matching_fit["relative_deviation"] < 1e-6
    assert mismatched_fit["extrapolation_check_status"] == "ok"
    assert mismatched_fit["relative_deviation"] > 0.05


@pytest.mark.parametrize("point_count", [3, 4])
def test_main_fit_survives_unavailable_extrapolation_check(point_count: int) -> None:
    sample_sizes = np.geomspace(10, 80, point_count)
    result = fit_learning_curves(
        power_records(
            asymptote=0.2,
            scale=1.8,
            rate=0.75,
            sample_sizes=sample_sizes,
        ),
        error_column="metric",
        forms=("power",),
    )
    fit = result.fits.iloc[0]
    assert np.isfinite(fit["asymptote"])
    assert fit["extrapolation_check_status"] == "insufficient_points"
    assert pd.isna(fit["predicted"])
    assert pd.isna(fit["observed"])
    assert pd.isna(fit["relative_deviation"])


@pytest.mark.parametrize(
    ("values", "orders"),
    [([0.6, 0.4, 0.5, 0.2], [1, 2, 3, 4]), ([1.0, 0.8, 0.95], [3, 6, 9])],
)
def test_isotonic_projection_is_nonincreasing_and_preserves_raw_values(
    values: list[float], orders: list[int]
) -> None:
    original = pd.DataFrame({"position": orders, "asymptote": values})
    result = monotonize_nonincreasing(original, order_column="position")
    ordered = result.sort_values("position")

    assert np.all(np.diff(ordered["running_minimum"].to_numpy()) <= 1e-12)
    assert np.all(np.diff(ordered["isotonic_value"].to_numpy()) <= 1e-12)
    assert np.all(ordered["running_minimum"].to_numpy() <= values)
    assert np.any(ordered["isotonic_value"].to_numpy() > np.asarray(values))
    assert result["raw_asymptote"].tolist() == values
    assert result["asymptote"].tolist() == values
    assert result["violates_nonincreasing"].any()


@pytest.mark.parametrize(
    ("records", "kwargs", "message"),
    [
        (
            pd.DataFrame({"N": [10.0, 20.0], "metric": [0.8, 0.6]}),
            {"error_column": "metric", "forms": ("power",)},
            "three distinct",
        ),
        (
            pd.DataFrame({"N": [10.0, 20.0, 40.0], "metric": [0.5, 0.5, 0.5]}),
            {"error_column": "metric", "forms": ("power",)},
            "all be equal",
        ),
        (
            pd.DataFrame({"N": [10.0, 20.0, 40.0], "metric": [0.8, np.nan, 0.4]}),
            {"error_column": "metric", "forms": ("power",)},
            "finite numeric",
        ),
    ],
)
def test_degenerate_inputs_fail_with_diagnostics(
    records: pd.DataFrame, kwargs: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        fit_learning_curves(records, **kwargs)


@pytest.mark.parametrize("square_error", [False, True])
def test_median_aggregation_and_envelope_are_public_and_generic(square_error: bool) -> None:
    frame = pd.DataFrame(
        {
            "collection": ["a"] * 12,
            "candidate": ["first"] * 6 + ["second"] * 6,
            "unit": [0, 1, 0, 1, 0, 1] * 2,
            "N": [10.0, 10.0, 20.0, 20.0, 40.0, 40.0] * 2,
            "metric": [0.8, 0.6, 0.55, 0.5, 0.4, 0.35, 0.7, 0.5, 0.6, 0.45, 0.5, 0.3],
        }
    )
    aggregate = aggregate_median_errors(
        frame,
        error_column="metric",
        group_columns=("collection", "candidate"),
        square_error=square_error,
    )
    assert aggregate["N"].nunique() == len(np.unique(frame["N"]))
    assert set(aggregate) == {
        "collection",
        "candidate",
        "N",
        "observed_error",
        "observation_count",
    }


@pytest.mark.parametrize("sample_sizes", [np.geomspace(8, 512, 7), np.geomspace(12, 768, 9)])
def test_default_forms_include_individual_series_and_envelope(sample_sizes: np.ndarray) -> None:
    rows = []
    for candidate, scale in (("first", 1.5), ("second", 1.0)):
        for unit, offset in enumerate((-0.002, 0.002)):
            for n_value in sample_sizes:
                rows.append(
                    {
                        "collection": "synthetic",
                        "candidate": candidate,
                        "unit": unit,
                        "N": float(n_value),
                        "metric": 0.15 + scale * n_value ** (-0.7) + offset,
                    }
                )
    result = fit_learning_curves(
        pd.DataFrame(rows),
        error_column="metric",
        group_columns=("collection", "candidate"),
        model_column="candidate",
    )

    assert set(result.fits["form"]) == {"power", "exponential"}
    assert set(result.fits["series_type"]) == {"individual", "envelope"}
    assert result.points.loc[
        result.points["series_type"].eq("envelope"), "candidate"
    ].isna().all()
    individual_counts = (
        result.points.loc[result.points["series_type"].eq("individual")]
        .groupby("N")["observation_count"]
        .sum()
    )
    envelope_counts = result.points.loc[
        result.points["series_type"].eq("envelope")
    ].set_index("N")["observation_count"]
    assert envelope_counts.equals(individual_counts)
    assert pd.api.types.is_integer_dtype(envelope_counts)


@pytest.mark.parametrize("test_variance", [0.25, 2.0])
def test_normalization_uses_explicit_test_variance(test_variance: float) -> None:
    result = normalize_asymptotes(
        pd.DataFrame({"asymptote": [0.1, 0.4]}), test_variance
    )
    assert result["normalized_asymptote"].tolist() == pytest.approx(
        [0.1 / test_variance, 0.4 / test_variance]
    )
