# TITAN walk-forward validation

TITAN V1 uses fixed rules rather than a fitted machine-learning model. The
walk-forward engine therefore performs expanding-window out-of-sample replay;
it does not claim to train or optimize parameters inside the training window.

Example:

```powershell
python -m app.main walk-forward `
  --history-start-year 2022 `
  --first-test-year 2023 `
  --last-test-year 2025 `
  --holding-days 20 `
  --interval-months 1 `
  --top-n 5 `
  --success-return 0.03
```

This creates the following folds:

```text
2022 history       -> test 2023
2022-2023 history  -> test 2024
2022-2024 history  -> test 2025
```

The strategy version and criteria remain frozen during each test fold. Monthly
selection dates are evaluated at the requested observed trading-session
horizon.

Artifacts are isolated from normal operation:

```text
output/walk_forward/selections/
output/walk_forward/observations/
output/walk_forward/market_data/
output/walk_forward/validations/
output/walk_forward/quality/
output/walk_forward/universe/
output/walk_forward/walk_forward_result.json
output/reports/walk_forward_validation.md
```

Fold errors and incomplete selection dates remain in the result rather than
being silently discarded. A result with non-COMPLETE point-in-time universe
coverage must be treated as provisional because survivorship bias may remain.
