# Cornerflick: candidate no-key source with actual match xG

27 Oct 2026. Technical sources:
- https://cornerflick.com/data
- https://cornerflick.com/football/leagues/premier-league/results/season.json
- https://cornerflick.com/football/premier-league/matches/arsenal-vs-coventry-premier-league-2026-08-21/data.json

Cornerflick explicitly offers JSON/CSV match records and releases *its compilation*
as CC BY 4.0 with attribution. It still warns that underlying rights belong to
upstream providers. Match provenance can identify API-Football. The latter
restricts re-sale and some betting-related publication uses; see:
https://www.api-football.com/terms

This experimental adapter and action make at most four GET requests in total:
two published league indexes, then ONE listed completed match per league.
No credentials, browsers, proxies, blocked provider endpoints, bulk pulls,
public republishing of match data or scheduled repeat jobs.
Each audit only logs counts and metric names, not per-match values.

A JSON data file has team names, kickoff, results, and statistics incl.
shots, shots on target, xG, corners, cards and possession *when provided*.
All optional fields remain null/missing when source does not supply them.

**IMPORTANT:** A CC BY licence for this compilation is not automatically a
licence for mass redistribution of its upstream provider's statistics or
operation as a data reseller. Verify rights/usage for paid PRIME SYNDICATE
before switching on full ingestion. No ingestion to the main MATCHPULSE here.
