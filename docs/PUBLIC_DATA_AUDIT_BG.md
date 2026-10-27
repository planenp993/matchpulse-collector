# Public football export audit — 27 October 2026

Evaluates publicly documented, keyless CSV datasets for MATCHPULSE.
The script makes only a single plain GET per CSV URL; no scraping,
credentials, repeated requests or data persistence. Prints only totals,
freshness and coverage. This is a one-time diagnostic, not production.

Candidates:
- Cornerflick: CC BY 4.0 compilation (commercial use with credit);
  underlying provider rights remain separate. Per-league published CSV.
- open-matchday: 75 league CSV project, updated daily, but STRICTLY
  informational and non-commercial. Underlying provider terms separate.
  Its CSV cannot be treated as authorised input to a paid tips product.
- Neither source claims comprehensive current xG.

See the workflow audit-public-exports.yml results for the actual HTTP
responses. No fetched third-party match records are persisted here.
