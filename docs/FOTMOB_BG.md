# FotMob experiment

Added `scripts/fotmob_adapter.py` and unit tests. This is an **offline parser** for locally supplied, authorized FotMob-format match statistics. It does not contact FotMob or schedule any scraping.

FotMob has explicitly objected to unauthorized automated retrieval: https://github.com/probberechts/soccerdata/issues/918

Expected fields: xG, total shots, shots on target, corners, yellow/red cards and possession, where available. Missing fields remain missing. Parser shape is preliminary and must be validated against a permitted real export before production use.

The existing OpenFootball collector and SofaScore experiment remain unchanged. The main MATCHPULSE repository is not touched.
