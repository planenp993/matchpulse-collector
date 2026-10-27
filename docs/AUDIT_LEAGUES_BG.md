# Audit methodology — Cornerflick league quality

One-off diagnostic only; not daily data harvesting. Covers 18 standard competitions shown in
the Cornerflick football-leagues catalog as of 2026-10-27. The 19th featured competition,
FIFA World Cup 2026, is a special hub rather than a standard league JSON season feed.
Fetches one published season index and two recently completed match JSON exports
per league; checks missing metrics (incl xG), home/away and score consistency.

Four European league indexes are independently compared by **exact normalized club names**,
date tolerance 1 day and final score with the CC0 openfootball/football.json feed. Many
unmatched records can reflect naming differences; they are NOT automatically false
fixtures. Names that coincide with country names in domestic leagues are separately flagged.
The report is printed to GitHub Actions logs; no provider data files are stored.

Results from this audit should be understood as evidence from a **small per-league sample**,
NOT proof that xG is present in all fixtures nor that each tournament is reliable.
Underlying rights for Cornerflick-sourced API-Football remain distinct from CC BY compilation.
No integration into the main MATCHPULSE application until reliability and rights verified.
