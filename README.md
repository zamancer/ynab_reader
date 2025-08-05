![Logo](./assets/ynab_reader_logo.webp)

# YNAB Reader

A project I started for the code used for a YNAB helper tool. 
The motivation of the tool is to help me consolidate the balances of some of my YNAB accounts.

## Getting started

Coming soon...

## Development

### Code Quality

This project uses [Ruff](https://docs.astral.sh/ruff/) for linting and formatting, and [MyPy](https://mypy.readthedocs.io/) for type checking.

#### Running Linting Locally

```bash
# Check code style and issues
ruff check .

# Auto-fix issues where possible
ruff check . --fix

# Format code
ruff format .

# Type checking
mypy .
```

#### VSCode Integration

For the best development experience, install these official extensions:

1. **Ruff Extension** (by Astral-sh)
   - Extension ID: `charliermarsh.ruff`
   - Provides real-time linting, formatting, and import sorting
   - Auto-fixes on save
   - Supports Jupyter notebooks

2. **Mypy Type Checker** (by Microsoft)
   - Extension ID: `ms-python.mypy-type-checker`
   - Real-time type checking with error highlighting
   - Supports workspace-wide type checking
   - Uses dmypy daemon for faster checking

**Recommended VSCode Settings:**

Add to your `.vscode/settings.json`:
```json
{
  "python.defaultInterpreterPath": "./venv/bin/python",
  "[python]": {
    "editor.defaultFormatter": "charliermarsh.ruff",
    "editor.formatOnSave": true,
    "editor.codeActionsOnSave": {
      "source.fixAll.ruff": "explicit",
      "source.organizeImports.ruff": "explicit"
    }
  },
  "mypy-type-checker.importStrategy": "fromEnvironment",
  "mypy-type-checker.reportingScope": "workspace"
}
```

#### Configuration

Linting and type checking configuration is defined in `pyproject.toml`. The setup includes:

- **Ruff**: Code linting, import sorting, and formatting with 88-character line length
- **MyPy**: Static type checking with Python 3.11 compatibility
