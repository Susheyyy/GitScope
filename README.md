# GitScope

Git history analyzer that turns repository commits into code hotspot, contributor work summary, and bus-factor risk reports.

GitScope answers core questions about any codebase:
1. **Who worked on what**: Contributor breakdown with line modifications, commit counts, and primary focus areas.
2. **Hotspots**: Which files and directories change most frequently and undergo the heaviest churn.
3. **Temporal Coupling**: Files that consistently change together, exposing hidden dependencies and architectural coupling.
4. **Ownership and Bus Factor**: Who knows each area of the codebase, and how concentrated that knowledge is.
5. **Commit Message Hygiene**: Quality score (0-100) scanning for vague messages, huge dump commits, and ticket references.

## How to Run

### Method 1: Interactive Web Dashboard & Local Server

Start the local web server:

Windows (PowerShell):
```powershell
$env:PYTHONPATH="src"; python -m cli serve
```

Linux / macOS:
```bash
PYTHONPATH=src python -m cli serve
```

Then open `http://127.0.0.1:8000` in your browser. Paste any local path (e.g. `.`) or remote GitHub repository URL to trigger background analysis, live status polling, and interactive reports with treemaps.

---

### Method 2: CLI Direct Execution

Windows (PowerShell):
```powershell
$env:PYTHONPATH="src"; python -m cli analyze <PATH_OR_URL>
```

Linux / macOS:
```bash
PYTHONPATH=src python -m cli analyze <PATH_OR_URL>
```

Examples:
```powershell
# Analyze the current local repository in terminal
$env:PYTHONPATH="src"; python -m cli analyze .

# Generate an interactive standalone HTML report (with treemap & filters)
$env:PYTHONPATH="src"; python -m cli analyze . --format html --output report.html

# Analyze a public remote GitHub repository
$env:PYTHONPATH="src"; python -m cli analyze https://github.com/Susheyyy/GitScope

# Filter by date range
$env:PYTHONPATH="src"; python -m cli analyze . --since "30 days ago"
$env:PYTHONPATH="src"; python -m cli analyze . --since "2024-01-01" --until "2024-12-31"

# Export report to Markdown
$env:PYTHONPATH="src"; python -m cli analyze . --format markdown --output report.md

# Export report to JSON
$env:PYTHONPATH="src"; python -m cli analyze . --format json --output report.json
```

---

### Method 3: Package Install (Enable `gitscope` CLI Command)

Install locally in editable mode:
```bash
pip install -e .
```

Run directly:
```bash
# Start Web Server
gitscope serve

# Run CLI analysis
gitscope analyze . --format html --output report.html
```

---

## Running Tests

Run the test suite using Python's built-in test runner:

Windows (PowerShell):
```powershell
$env:PYTHONPATH="src"; python -m unittest discover tests
```

Linux / macOS:
```bash
PYTHONPATH=src python -m unittest discover tests
```
