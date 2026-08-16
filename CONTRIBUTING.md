# Contributing to Seedance Prompts

Thank you for considering contributing to `seedance-prompts`!

## How to Contribute

1. **Bug Reports & Feature Requests**: Open an issue describing the problem or requested feature.
2. **Adding Prompt Examples**: Submit a PR with additions or improvements to `scripts/seedance_query.py` or new categorization logic.
3. **Scraper Improvements**: If `bestseedanceprompts.com` updates its HTML structure, PRs updating `scripts/seedance_scraper.py` are welcome.

## Development Workflow

```bash
# Clone the repository
git clone https://github.com/ardha27/seedance-prompts.git
cd seedance-prompts

# Populate the local database (scrapes 1,500+ prompts)
python3 scripts/seedance_scraper.py full

# Query and test search functionality
python3 scripts/seedance_query.py "cinematic vlog"

# Score a custom prompt
python3 scripts/seedance_query.py --score "Your prompt text here"
```

## Guidelines
- Follow standard PEP 8 Python formatting.
- Ensure all search and scoring scripts run without third-party dependencies beyond standard library + sqlite3.
