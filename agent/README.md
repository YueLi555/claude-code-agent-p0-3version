# Minimal Tool-Using Agent Runtime

A minimal single-agent runtime for coding, file, and shell tasks.

## Current scope
This is a P0 skeleton with:
- tool-use loop
- permission gating
- CLI entrypoint
- local tests
- stub model support

## Project structure
- `core/` runtime core
- `tools/` built-in tools
- `adapters/` model adapter
- `cli/` command-line entrypoint
- `tests/` smoke tests

## Run tests
```bash
python -m pytest tests/test_loop.py -v
```

## Run with stub model
```bash
python -m cli.main --prompt "list the files in this directory" --stub --headless
```