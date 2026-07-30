# Point-in-time stock universe

TITAN accepts the following optional columns in `kospi.csv` and `kosdaq.csv`:

```text
code,name,market,effective_from,effective_to
```

- `effective_from`: first date on which the row is valid.
- `effective_to`: last date on which the row is valid.
- Multiple rows may represent market migrations when the source is curated as
  a complete historical dataset.

Historical completeness must never be inferred from populated dates. The
source directory must contain `universe_manifest.json`:

```json
{
  "point_in_time_complete": true
}
```

Set this value to `true` only when the source includes delisted securities and
historical market membership. Otherwise TITAN reports `PARTIAL` or `UNKNOWN`
coverage and warns that survivorship bias may remain.
