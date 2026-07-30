# TITAN observation cohort

The observation cohort is a bounded statistical sample. It is not a stock
recommendation and does not change the V1 selection threshold.

## Policy

- Selected candidates: unchanged, normalized score 80 or higher and all hard
  filters must pass.
- Observation candidates: normalized score 70 through 79.
- Daily observation limit: 5.
- Ordering: score descending, then current trading value descending.
- Scores below 70 are not stored.

Selected and observation artifacts remain separated:

- `output/selections/`
- `output/observations/`
- `output/validations/`
- `output/observation_validations/`

## Commands

Create the selected and observation snapshots together:

```powershell
python -m app.main select --date 2026-07-27 --top-n 5
```

Validate the observation sample at multiple trading-session horizons:

```powershell
python -m app.main validate-observations `
  --selection-date 2026-07-27 `
  --as-of 2026-09-30 `
  --holding-days 5 10 20 40 `
  --success-return 0.03
```

Compare selected and observation score bands:

```powershell
python -m app.main calibration-report
```

The calibration report combines the two cohorts only for score-band analysis.
The normal cumulative selection report continues to exclude observations.
