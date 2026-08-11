# Fragile Families Challenge application

## Role in the research program

The repository-level research program studies how out-of-sample predictability
changes jointly with the observation horizon and the amount of available data.
For each outcome, the intended empirical object is a surface whose axes are a
linked data-scale path of paired \((N,K)\) values, the latest observed FFCWS
wave, and predictive performance. Fixed-\(K\), fixed-\(N\), and matched-\(K\)
slices provide the diagnostics needed to interpret that surface and, where
extrapolation is credible, estimate an upper bound on unpredictability.

The complete research objective and the distinction between the main study and
its GPA demonstration are defined in the repository [`README.md`](../README.md).
This `project/` directory contains the runnable data adapter and analysis
assets. Its current implemented scope prepares information observed from birth
through age 9 for six age-15 outcomes. The first planned methods demonstration
uses GPA only; it is not the final scope of the research program.

| Outcome | Code in the analysis data | Type |
|---|---|---|
| Grade point average | `gpa` | Continuous |
| Grit | `grit` | Continuous |
| Household eviction | `eviction` | Binary |
| Household material hardship | `materialHardship` | Continuous |
| Caregiver layoff | `layoff` | Binary |
| Caregiver job training | `jobTraining` | Binary |

These outcomes and the predefined training and test samples follow the Fragile
Families Challenge. See the
[special-collection introduction](https://pmc.ncbi.nlm.nih.gov/articles/PMC10260255/)
for the study design.

## Data and research design

Eligible predictors come from the background survey data collected before the
age-15 outcomes. Predictor eligibility, categorical value sets, and
prevalence-based screening are determined using the predefined training sample
only. The test sample is reserved for evaluating predictive performance.

Predictors use a single fixed representation, `median_mode`: categorical
variables become grouped indicator columns, and missing values are imputed
within whichever training subsample the engine selects. Two alternative
representations remain implemented under `strategies/` but are not enabled
and are not part of the research design.

The analysis repeatedly varies \(N\) and \(K\), fits each model on the selected
training data, and evaluates predictions on the predefined test sample. A
categorical variable's encoded columns are selected together and count as one
predictor variable.

## Reproduction

```text
project/
├── adapter.py
├── config/ffc.yaml
├── src/ffcws_data_processor/
├── tests/
├── schema/
├── data/
│   ├── private/        source data; excluded from Git
│   ├── adapter_work/   generated validation records; excluded from Git
│   └── ard/            generated analysis-ready data; excluded from Git
├── panels.yaml
├── model_params.yaml
├── requirements.txt
├── ADAPTER.md
└── README.md
```

Run project commands from `project/`:

```bash
../.venv/bin/python -m pip install -r requirements.txt
../.venv/bin/python adapter.py
../.venv/bin/python -m pytest -q
../.venv/bin/aleatoric-nk-grid-panels --manifest panels.yaml --dry-run
```

The N x K sweep engine is an external dependency pinned to a specific commit in
[`requirements.txt`](requirements.txt); changing that commit can change numerical
results and requires re-running the baseline recorded in
[`TESTS.md`](../TESTS.md). See the
[FFCWS data-preparation guide](ADAPTER.md) for representation and validation
details.
