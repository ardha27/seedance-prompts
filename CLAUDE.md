# Agent Instructions for Seedance Prompts

This repository provides an autonomous AI prompt engineering engine and database query interface for ByteDance Seedance 2.0 and Seedance 2.5 video generation.

## Key Files
- `scripts/seedance_query.py`: Search DB, analyze patterns, and score custom prompt quality (0-100).
- `scripts/seedance_scraper.py`: Concurrently fetches and indexes prompt cards from bestseedanceprompts.com into `~/.hermes/data/seedance_prompts.db`.
- `SKILL.md`: Hermes Agent skill spec for Seedance 2.0/2.5 prompt generation.

## Common CLI Commands
```bash
python3 scripts/seedance_query.py "cinematic night vlog"
python3 scripts/seedance_query.py --score "A young woman walking in Tokyo in slow motion"
python3 scripts/seedance_query.py --stats
python3 scripts/seedance_scraper.py update
```
