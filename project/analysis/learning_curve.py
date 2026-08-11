"""Generic learning-curve estimation from tabular sample-size/error records.

The module is deliberately independent of any particular data source.  Callers
provide column names and grouping keys; this module never reads input files or
imports a model-training package.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Collection, Literal, Sequence
import warnings

import numpy as np
import pandas as pd
from scipy.optimize import OptimizeWarning, curve_fit


CurveForm = Literal["power", "exponential"]
_PARAMETER_COUNT = 3
_SUPPORTED_FORMS: frozenset[str] = frozenset({"power", "exponential"})


@dataclass(frozen=True)
class LearningCurveResult:
    """Tabular outputs from fitting individual series and, when requested, an envelope.

    ``points`` contains the median observation at every available sample size.
    ``fits`` contains one row per series and curve form, including the held-out
    maximum-sample-size extrapolation check.
    """

    points: pd.DataFrame
    fits: pd.DataFrame
    excluded_row_count: int
    excluded_row_ratio: float


def aggregate_median_errors(
    records: pd.DataFrame,
    *,
    n_column: str = "N",
    error_column: str = "rmse",
    group_columns: Sequence[str] = (),
    square_error: bool = False,
) -> pd.DataFrame:
    """Aggregate repeated observations by their median error at each sample size.

    The returned ``observed_error`` is on the requested fitting scale.  Setting
    ``square_error=True`` converts an error such as RMSE to squared-error scale
    before aggregation.
    """

    groups = _normalise_group_columns(group_columns, n_column, error_column)
    _validate_record_columns(records, [n_column, error_column, *groups])
    if records.empty:
        raise ValueError("records must contain at least one row")

    frame = records.loc[:, [*groups, n_column, error_column]].copy()
    n_values = pd.to_numeric(frame[n_column], errors="coerce")
    errors = pd.to_numeric(frame[error_column], errors="coerce")
    if n_values.isna().any() or not np.isfinite(n_values.to_numpy()).all():
        raise ValueError(f"{n_column!r} must contain only finite numeric values")
    if (n_values <= 0).any():
        raise ValueError(f"{n_column!r} must contain only positive values")
    if errors.isna().any() or not np.isfinite(errors.to_numpy()).all():
        raise ValueError(f"{error_column!r} must contain only finite numeric values")
    if (errors < 0).any():
        raise ValueError(f"{error_column!r} must contain only non-negative values")
    if groups and frame.loc[:, groups].isna().any().any():
        raise ValueError("group columns must not contain missing values")

    frame[n_column] = n_values.astype(float)
    frame["_fitting_error"] = errors.pow(2) if square_error else errors.astype(float)
    keys = [*groups, n_column]
    result = (
        frame.groupby(keys, sort=True, dropna=False)["_fitting_error"]
        .agg(observed_error="median", observation_count="size")
        .reset_index()
    )
    return result


def fit_learning_curves(
    records: pd.DataFrame,
    *,
    n_column: str = "N",
    error_column: str = "rmse",
    group_columns: Sequence[str] = (),
    model_column: str | None = None,
    square_error: bool = False,
    forms: Sequence[CurveForm] = ("power", "exponential"),
    extrapolation_cutoff: float | None = None,
    validity_column: str | None = None,
    validity_values: Collection[object] | None = None,
    exclusion_flag_columns: Sequence[str] = (),
) -> LearningCurveResult:
    """Fit constrained curves and an optional pointwise-minimum model envelope.

    Every individual group receives every requested form.  If ``model_column``
    is supplied, it must be one of ``group_columns``; its values are minimised
    at each sample size to form an additional ``series_type == 'envelope'``.
    The extrapolation check fits only observations at or below the supplied
    cutoff (the median available sample size by default) and predicts the
    observed maximum sample size.

    Callers may provide a validity column and its accepted values, plus any
    number of boolean exclusion-flag columns.  Rows outside the accepted set
    or with a true flag are removed before median aggregation.  The returned
    counts make that data-quality decision available to every downstream
    consumer without encoding any source-specific output column names here.
    """

    groups = _normalise_group_columns(group_columns, n_column, error_column)
    forms = _normalise_forms(forms)
    if model_column is not None and model_column not in groups:
        raise ValueError("model_column must be included in group_columns")

    filtered_records, excluded_row_count, excluded_row_ratio = _filter_records(
        records,
        validity_column=validity_column,
        validity_values=validity_values,
        exclusion_flag_columns=exclusion_flag_columns,
    )

    aggregate = aggregate_median_errors(
        filtered_records,
        n_column=n_column,
        error_column=error_column,
        group_columns=groups,
        square_error=square_error,
    )
    individual_points = aggregate.assign(series_type="individual")
    all_points = [individual_points]
    series: list[tuple[dict[str, object], str, pd.DataFrame]] = []

    for values, points in _iter_groups(aggregate, groups):
        series.append((values, "individual", points))

    if model_column is not None:
        envelope_groups = [column for column in groups if column != model_column]
        envelope = _pointwise_envelope(aggregate, n_column, envelope_groups)
        envelope[model_column] = pd.NA
        envelope = envelope.loc[:, [*groups, n_column, "observed_error", "observation_count"]]
        all_points.append(envelope.assign(series_type="envelope"))
        for values, points in _iter_groups(envelope, envelope_groups):
            values[model_column] = pd.NA
            series.append((values, "envelope", points))

    fit_rows: list[dict[str, object]] = []
    for values, series_type, points in series:
        fit_rows.extend(
            _fit_series(
                points,
                group_values=values,
                series_type=series_type,
                n_column=n_column,
                forms=forms,
                extrapolation_cutoff=extrapolation_cutoff,
            )
        )

    return LearningCurveResult(
        points=pd.concat(all_points, ignore_index=True),
        fits=pd.DataFrame(fit_rows),
        excluded_row_count=excluded_row_count,
        excluded_row_ratio=excluded_row_ratio,
    )


def bootstrap_asymptote_intervals(
    records: pd.DataFrame,
    *,
    sample_column: str,
    n_column: str = "N",
    error_column: str = "rmse",
    group_columns: Sequence[str] = (),
    model_column: str | None = None,
    square_error: bool = False,
    forms: Sequence[CurveForm] = ("power", "exponential"),
    extrapolation_cutoff: float | None = None,
    validity_column: str | None = None,
    validity_values: Collection[object] | None = None,
    exclusion_flag_columns: Sequence[str] = (),
    iterations: int,
    confidence_level: float,
    random_seed: int,
) -> pd.DataFrame:
    """Return shared-unit bootstrap intervals for every fitted asymptote.

    ``sample_column`` identifies the unit to resample. A single sampled multiset
    is applied to every group, preserving their pairing; all rows for each unit
    are retained together, so repeated measurements are never resampled as
    independent cells. Failed bootstrap refits are counted in the result
    instead of being silently treated as successful draws.
    """

    if iterations < 1:
        raise ValueError("iterations must be at least 1")
    if not 0 < confidence_level < 1:
        raise ValueError("confidence_level must be strictly between 0 and 1")
    filtered_records, _, _ = _filter_records(
        records,
        validity_column=validity_column,
        validity_values=validity_values,
        exclusion_flag_columns=exclusion_flag_columns,
    )
    _validate_record_columns(filtered_records, [sample_column])

    groups = _normalise_group_columns(group_columns, n_column, error_column)
    base_result = fit_learning_curves(
        records,
        n_column=n_column,
        error_column=error_column,
        group_columns=groups,
        model_column=model_column,
        square_error=square_error,
        forms=forms,
        extrapolation_cutoff=extrapolation_cutoff,
        validity_column=validity_column,
        validity_values=validity_values,
        exclusion_flag_columns=exclusion_flag_columns,
    )
    base = base_result.fits
    rng = np.random.default_rng(random_seed)
    samples: list[pd.DataFrame] = []
    failures = 0
    for iteration in range(iterations):
        resampled = _resample_units(filtered_records, sample_column, groups, rng)
        try:
            draw = fit_learning_curves(
                resampled,
                n_column=n_column,
                error_column=error_column,
                group_columns=groups,
                model_column=model_column,
                square_error=square_error,
                forms=forms,
                extrapolation_cutoff=extrapolation_cutoff,
            ).fits
        except (RuntimeError, ValueError):
            failures += 1
            continue
        draw = draw.assign(bootstrap_iteration=iteration)
        samples.append(draw)

    if not samples:
        raise RuntimeError("all bootstrap refits failed")

    key_columns = [*groups, "series_type", "form"]
    successful = pd.concat(samples, ignore_index=True)
    interval_rows: list[dict[str, object]] = []
    lower_quantile = (1.0 - confidence_level) / 2.0
    upper_quantile = 1.0 - lower_quantile
    for values, base_rows in _iter_groups(base, key_columns):
        mask = np.ones(len(successful), dtype=bool)
        for column, value in values.items():
            if pd.isna(value):
                mask &= successful[column].isna().to_numpy()
            else:
                mask &= successful[column].eq(value).to_numpy()
        distribution = successful.loc[mask, "asymptote"].to_numpy(dtype=float)
        if distribution.size == 0:
            raise RuntimeError("a bootstrap refit omitted a required fitted series")
        row = base_rows.iloc[0].to_dict()
        row["asymptote_lower"] = float(np.quantile(distribution, lower_quantile))
        row["asymptote_upper"] = float(np.quantile(distribution, upper_quantile))
        row["bootstrap_successes"] = int(distribution.size)
        row["bootstrap_failures"] = failures
        row["bootstrap_iterations"] = iterations
        row["confidence_level"] = confidence_level
        row["excluded_row_count"] = base_result.excluded_row_count
        row["excluded_row_ratio"] = base_result.excluded_row_ratio
        interval_rows.append(row)
    return pd.DataFrame(interval_rows)


def monotonize_nonincreasing(
    estimates: pd.DataFrame,
    *,
    order_column: str,
    value_column: str = "asymptote",
    group_columns: Sequence[str] = (),
    running_minimum_column: str = "running_minimum",
    output_column: str = "isotonic_value",
) -> pd.DataFrame:
    """Preserve raw estimates and add two non-increasing adjustments.

    ``running_minimum_column`` is the primary one-sided estimate: it can only
    decrease an original value. ``output_column`` is the L2 isotonic projection
    retained as a comparison, and can increase individual original values.
    """

    groups = _normalise_group_columns(group_columns, order_column, value_column)
    _validate_record_columns(estimates, [order_column, value_column, *groups])
    result = estimates.copy()
    values = pd.to_numeric(result[value_column], errors="coerce")
    order = pd.to_numeric(result[order_column], errors="coerce")
    if values.isna().any() or not np.isfinite(values.to_numpy()).all():
        raise ValueError(f"{value_column!r} must contain only finite numeric values")
    if order.isna().any() or not np.isfinite(order.to_numpy()).all():
        raise ValueError(f"{order_column!r} must contain only finite numeric values")
    if result.duplicated([*groups, order_column]).any():
        raise ValueError("each group must have at most one estimate per order value")

    result[f"raw_{value_column}"] = values.astype(float)
    result[running_minimum_column] = np.nan
    result[output_column] = np.nan
    result["violates_nonincreasing"] = False
    for _, subset in _iter_groups(result, groups):
        ordered = subset.sort_values(order_column)
        raw = ordered[value_column].to_numpy(dtype=float)
        result.loc[ordered.index, running_minimum_column] = np.minimum.accumulate(raw)
        projected = _pava_nonincreasing(raw)
        result.loc[ordered.index, output_column] = projected
        violations = np.r_[False, np.diff(raw) > 0]
        result.loc[ordered.index, "violates_nonincreasing"] = violations
    return result


def normalize_asymptotes(
    estimates: pd.DataFrame,
    test_variance: float,
    *,
    asymptote_column: str = "asymptote",
    output_column: str = "normalized_asymptote",
) -> pd.DataFrame:
    """Divide asymptote estimates by an explicitly supplied test-set variance."""

    _validate_record_columns(estimates, [asymptote_column])
    if not np.isfinite(test_variance) or test_variance <= 0:
        raise ValueError("test_variance must be a finite positive value")
    result = estimates.copy()
    asymptotes = pd.to_numeric(result[asymptote_column], errors="coerce")
    if asymptotes.isna().any() or not np.isfinite(asymptotes.to_numpy()).all():
        raise ValueError(f"{asymptote_column!r} must contain only finite numeric values")
    result[output_column] = asymptotes / test_variance
    return result


def _filter_records(
    records: pd.DataFrame,
    *,
    validity_column: str | None,
    validity_values: Collection[object] | None,
    exclusion_flag_columns: Sequence[str],
) -> tuple[pd.DataFrame, int, float]:
    """Apply caller-declared row validity rules before any aggregation."""

    flags = list(exclusion_flag_columns)
    if len(flags) != len(set(flags)):
        raise ValueError("exclusion_flag_columns must not contain duplicates")
    if validity_column is None and validity_values is not None:
        raise ValueError("validity_values requires validity_column")
    if validity_column is not None and validity_values is None:
        raise ValueError("validity_column requires validity_values")

    required = [*flags]
    if validity_column is not None:
        required.append(validity_column)
    _validate_record_columns(records, required)

    keep = pd.Series(True, index=records.index, dtype=bool)
    if validity_column is not None:
        accepted = list(validity_values)
        if not accepted:
            raise ValueError("validity_values must not be empty when validity_column is set")
        keep &= records[validity_column].isin(accepted)
    for column in flags:
        keep &= ~records[column].fillna(False).astype(bool)

    excluded_row_count = int((~keep).sum())
    excluded_row_ratio = (
        excluded_row_count / len(records) if len(records) else 0.0
    )
    return records.loc[keep].copy(), excluded_row_count, excluded_row_ratio


def _fit_series(
    points: pd.DataFrame,
    *,
    group_values: dict[str, object],
    series_type: str,
    n_column: str,
    forms: Sequence[CurveForm],
    extrapolation_cutoff: float | None,
) -> list[dict[str, object]]:
    n_values = points[n_column].to_numpy(dtype=float)
    errors = points["observed_error"].to_numpy(dtype=float)
    _validate_curve_data(n_values, errors)
    cutoff = float(np.median(n_values) if extrapolation_cutoff is None else extrapolation_cutoff)
    maximum_n = float(np.max(n_values))
    training = n_values <= cutoff
    rows: list[dict[str, object]] = []
    for form in forms:
        asymptote, scale, rate = _fit_parameters(n_values, errors, form)
        predicted, observed, relative_deviation, check_status = _extrapolation_check(
            n_values=n_values,
            errors=errors,
            form=form,
            cutoff=cutoff,
            maximum_n=maximum_n,
            training=training,
        )
        rows.append(
            {
                **group_values,
                "series_type": series_type,
                "form": form,
                "asymptote": asymptote,
                "scale": scale,
                "rate": rate,
                "extrapolation_cutoff": cutoff,
                "extrapolation_n": maximum_n,
                "predicted": predicted,
                "observed": observed,
                "relative_deviation": relative_deviation,
                "extrapolation_check_status": check_status,
            }
        )
    return rows


def _extrapolation_check(
    *,
    n_values: np.ndarray,
    errors: np.ndarray,
    form: CurveForm,
    cutoff: float,
    maximum_n: float,
    training: np.ndarray,
) -> tuple[float, float, float, str]:
    if cutoff >= maximum_n:
        return (np.nan, np.nan, np.nan, "invalid_cutoff")
    if np.count_nonzero(training) < _PARAMETER_COUNT:
        return (np.nan, np.nan, np.nan, "insufficient_points")
    try:
        asymptote, scale, rate = _fit_parameters(
            n_values[training], errors[training], form
        )
    except (RuntimeError, ValueError):
        return (np.nan, np.nan, np.nan, "fit_failed")
    observed = float(errors[np.argmax(n_values)])
    predicted = float(_curve_function(form, maximum_n, asymptote, scale, rate))
    relative_deviation = abs(predicted - observed) / max(
        abs(observed), np.finfo(float).eps
    )
    return (predicted, observed, relative_deviation, "ok")


def _fit_parameters(
    n_values: np.ndarray,
    errors: np.ndarray,
    form: CurveForm,
) -> tuple[float, float, float]:
    _validate_curve_data(n_values, errors)

    smallest = max(float(np.min(errors)) * 0.8, 0.0)
    scale = max(float(np.ptp(errors)), np.finfo(float).eps)
    initial_rate = 0.5 if form == "power" else 1.0 / float(np.median(n_values))
    function = _power_curve if form == "power" else _exponential_curve
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", OptimizeWarning)
        try:
            parameters, _ = curve_fit(
                function,
                n_values,
                errors,
                p0=(smallest, scale, initial_rate),
                bounds=([0.0, 0.0, 0.0], [np.inf, np.inf, np.inf]),
                maxfev=50_000,
            )
        except (OptimizeWarning, RuntimeError, ValueError) as error:
            raise RuntimeError(f"{form} curve fit failed: {error}") from error
    return tuple(float(parameter) for parameter in parameters)


def _validate_curve_data(n_values: np.ndarray, errors: np.ndarray) -> None:
    if n_values.size < _PARAMETER_COUNT:
        raise ValueError("at least three distinct sample-size points are required")
    if np.unique(n_values).size < _PARAMETER_COUNT:
        raise ValueError("at least three distinct sample-size points are required")
    if np.ptp(errors) <= np.finfo(float).eps * max(1.0, float(np.max(np.abs(errors)))):
        raise ValueError("errors must not all be equal")


def _power_curve(n_values: np.ndarray | float, asymptote: float, scale: float, rate: float) -> np.ndarray | float:
    return asymptote + scale * np.power(n_values, -rate)


def _exponential_curve(n_values: np.ndarray | float, asymptote: float, scale: float, rate: float) -> np.ndarray | float:
    return asymptote + scale * np.exp(-rate * np.asarray(n_values))


def _curve_function(form: CurveForm, n_value: float, asymptote: float, scale: float, rate: float) -> float:
    function = _power_curve if form == "power" else _exponential_curve
    return float(function(n_value, asymptote, scale, rate))


def _pointwise_envelope(
    aggregate: pd.DataFrame,
    n_column: str,
    envelope_groups: Sequence[str],
) -> pd.DataFrame:
    keys = [*envelope_groups, n_column]
    return (
        aggregate.groupby(keys, sort=True, dropna=False)
        .agg(
            observed_error=("observed_error", "min"),
            observation_count=("observation_count", "sum"),
        )
        .reset_index()
    )


def _resample_units(
    records: pd.DataFrame,
    sample_column: str,
    group_columns: Sequence[str],
    rng: np.random.Generator,
) -> pd.DataFrame:
    if records[sample_column].isna().any():
        raise ValueError("sample_column must not contain missing values")
    units = records[sample_column].unique()
    if units.size < 2:
        raise ValueError("bootstrap requires at least two sample units")
    expected_units = set(units.tolist())
    for _, subset in _iter_groups(records, group_columns):
        group_units = set(subset[sample_column].unique().tolist())
        if group_units != expected_units:
            raise ValueError("each bootstrap group must contain the same sample units")

    selected = rng.choice(units, size=units.size, replace=True)
    pieces: list[pd.DataFrame] = []
    for unit in selected:
        pieces.append(records.loc[records[sample_column].eq(unit)].copy())
    return pd.concat(pieces, ignore_index=True)


def _pava_nonincreasing(values: np.ndarray) -> np.ndarray:
    """Unit-weight pool-adjacent-violators projection onto decreasing sequences."""

    means: list[float] = []
    counts: list[int] = []
    for value in -values:
        means.append(float(value))
        counts.append(1)
        while len(means) >= 2 and means[-2] > means[-1]:
            total = counts[-2] + counts[-1]
            means[-2] = (means[-2] * counts[-2] + means[-1] * counts[-1]) / total
            counts[-2] = total
            means.pop()
            counts.pop()
    expanded = np.concatenate(
        [np.full(count, mean, dtype=float) for mean, count in zip(means, counts)]
    )
    return -expanded


def _iter_groups(
    frame: pd.DataFrame,
    group_columns: Sequence[str],
) -> list[tuple[dict[str, object], pd.DataFrame]]:
    columns = list(group_columns)
    if not columns:
        return [({}, frame)]
    grouped: list[tuple[dict[str, object], pd.DataFrame]] = []
    for key, subset in frame.groupby(columns, sort=True, dropna=False):
        key_values = key if isinstance(key, tuple) else (key,)
        grouped.append((dict(zip(columns, key_values, strict=True)), subset))
    return grouped


def _normalise_group_columns(
    group_columns: Sequence[str],
    *reserved_columns: str,
) -> list[str]:
    groups = list(group_columns)
    if len(groups) != len(set(groups)):
        raise ValueError("group_columns must not contain duplicates")
    if set(groups).intersection(reserved_columns):
        raise ValueError("group_columns must not repeat a measurement column")
    return groups


def _normalise_forms(forms: Sequence[CurveForm]) -> tuple[CurveForm, ...]:
    requested = tuple(forms)
    if not requested:
        raise ValueError("at least one curve form is required")
    if len(requested) != len(set(requested)) or not set(requested).issubset(_SUPPORTED_FORMS):
        raise ValueError("forms must be unique selections of 'power' and 'exponential'")
    return requested


def _validate_record_columns(frame: pd.DataFrame, columns: Sequence[str]) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"missing required columns: {missing}")
