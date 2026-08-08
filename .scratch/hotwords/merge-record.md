# Merge record: hotwords

Date: 2026-08-08
Target branch: `main`
Source branch: `feature/hotwords`
Merge commit: `6c3e3a6e4d83b66f181b83e6f7f7cc3729622a7c`

## Result

`feature/hotwords` was merged into `main` with a non-fast-forward merge.

## Verification

- Working tree: clean after the merge.
- Command: `python -m pytest -q tests/integration/test_hotwords.py tests/integration/test_openapi.py`
- Result: not executed because the environment is missing the `psycopg` module required by `tests/integration/conftest.py`.
