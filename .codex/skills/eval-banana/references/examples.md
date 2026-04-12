# Example check patterns

Gallery of real-world eval-banana check patterns. Copy and adapt.

## Table of contents

- Deterministic: file existence and content
- Deterministic: JSON schema validation
- Deterministic: no forbidden tokens in source
- Deterministic: counting records
- LLM judge: README quality
- LLM judge: tone / professionalism
- LLM judge: factual consistency
- LLM judge: multi-file comparison
- Task-based: run the test suite
- Task-based: run a linter
- Task-based: API smoke test
- Task-based: Playwright UI flow

## Deterministic: file existence and content

```yaml
schema_version: 1
id: changelog_exists_and_nonempty
type: deterministic
description: CHANGELOG.md exists and is at least 200 chars.
target_paths:
  - CHANGELOG.md
script: |
  import json, sys
  from pathlib import Path

  ctx = json.loads(Path(sys.argv[1]).read_text())
  target = ctx["targets"][0]
  if not target["exists"]:
      print(f"missing: {target['path']}", file=sys.stderr)
      sys.exit(1)
  content = Path(target["resolved_path"]).read_text(encoding="utf-8")
  if len(content) < 200:
      print(f"only {len(content)} chars", file=sys.stderr)
      sys.exit(1)
```

## Deterministic: JSON schema validation

```yaml
schema_version: 1
id: output_matches_schema
type: deterministic
description: output.json has required top-level keys and correct types.
target_paths:
  - output.json
script: |
  import json, sys
  from pathlib import Path

  ctx = json.loads(Path(sys.argv[1]).read_text())
  target = ctx["targets"][0]
  data = json.loads(Path(target["resolved_path"]).read_text())

  required = {"id": str, "created_at": str, "items": list}
  for key, expected_type in required.items():
      if key not in data:
          print(f"missing key: {key}", file=sys.stderr)
          sys.exit(1)
      if not isinstance(data[key], expected_type):
          print(f"{key} should be {expected_type.__name__}", file=sys.stderr)
          sys.exit(1)
  if not data["items"]:
      print("items is empty", file=sys.stderr)
      sys.exit(1)
```

## Deterministic: no forbidden tokens in source

```yaml
schema_version: 1
id: no_print_statements_in_src
type: deterministic
description: No print() calls in src/ (should use logging).
target_paths:
  - src
script: |
  import json, re, sys
  from pathlib import Path

  ctx = json.loads(Path(sys.argv[1]).read_text())
  src_dir = Path(ctx["targets"][0]["resolved_path"])
  pattern = re.compile(r"\bprint\(")
  offenders = []
  for py_file in src_dir.rglob("*.py"):
      text = py_file.read_text(encoding="utf-8")
      for line_no, line in enumerate(text.splitlines(), 1):
          # Skip comments and docstrings (naive but fine for most cases)
          if line.strip().startswith("#"):
              continue
          if pattern.search(line):
              offenders.append(f"{py_file}:{line_no}")
  if offenders:
      print("\n".join(offenders[:10]), file=sys.stderr)
      sys.exit(1)
```

## Deterministic: counting records

```yaml
schema_version: 1
id: users_csv_has_enough_rows
type: deterministic
description: users.csv has at least 100 rows (excluding header).
target_paths:
  - data/users.csv
script: |
  import csv, json, sys
  from pathlib import Path

  ctx = json.loads(Path(sys.argv[1]).read_text())
  path = Path(ctx["targets"][0]["resolved_path"])
  with path.open() as f:
      reader = csv.reader(f)
      next(reader, None)  # Skip header
      row_count = sum(1 for _ in reader)
  if row_count < 100:
      print(f"only {row_count} rows", file=sys.stderr)
      sys.exit(1)
```

## LLM judge: README quality

```yaml
schema_version: 1
id: readme_has_quickstart
type: llm_judge
description: README contains a quickstart that a new user can follow in under 5 minutes.
target_paths:
  - README.md
instructions: |
  Look for a "Quick start" or "Getting started" section in the README.
  Score 1 ONLY if it contains: (1) an install command, (2) a minimum
  config step if required, and (3) at least one example command to run.
  Score 0 if any of these are missing or unclear.
```

## LLM judge: tone / professionalism

```yaml
schema_version: 1
id: error_messages_are_helpful
type: llm_judge
description: Error messages in errors.log are helpful and professional.
target_paths:
  - errors.log
instructions: |
  Read the error messages in the log. Score 1 if they: (a) explain what
  went wrong in plain language, (b) suggest what to do next, and (c) do
  NOT expose stack traces or internal paths to end users. Score 0 if
  any message is cryptic, blames the user, or leaks internals.
```

## LLM judge: factual consistency

```yaml
schema_version: 1
id: summary_matches_source
type: llm_judge
description: The generated summary accurately reflects the source data.
target_paths:
  - summary.md
  - source_data.json
instructions: |
  Compare the claims in summary.md against the facts in source_data.json.
  Score 1 if every numeric claim, name, and date in the summary can be
  verified from the source data. Score 0 if ANY claim is fabricated,
  hallucinated, or contradicts the source.
```

## LLM judge: multi-file comparison

```yaml
schema_version: 1
id: docs_consistent_with_code
type: llm_judge
description: API docs describe the actual endpoints implemented in routes.py.
target_paths:
  - docs/api.md
  - src/routes.py
instructions: |
  For each endpoint documented in docs/api.md, check if it exists in
  src/routes.py. Score 1 if every documented endpoint is implemented
  AND every public endpoint in routes.py is documented. Score 0 if
  there is any drift between the two files.
```

## Task-based: run the test suite

```yaml
schema_version: 1
id: pytest_passes
type: task_based
description: The unit test suite passes.
command:
  - uv
  - run
  - pytest
  - tests
  - -q
```

## Task-based: run a linter

```yaml
schema_version: 1
id: ruff_clean
type: task_based
description: Ruff finds no lint issues in src/.
command:
  - uv
  - run
  - ruff
  - check
  - src
```

## Task-based: API smoke test

```yaml
schema_version: 1
id: health_endpoint_returns_200
type: task_based
description: The /health endpoint returns HTTP 200.
command:
  - bash
  - -c
  - 'curl -sf http://localhost:8000/health > /dev/null'
```

Note: using `bash -c` here because the check needs a pipe/redirect. For simpler checks prefer passing args directly without a shell.

## Task-based: Playwright UI flow

```yaml
schema_version: 1
id: login_flow_works
type: task_based
description: The login flow completes successfully in a headless browser.
command:
  - uv
  - run
  - python
  - ui_tests/login_flow.py
working_directory: .
env:
  HEADLESS: "1"
  BASE_URL: "http://localhost:3000"
```

The referenced `ui_tests/login_flow.py` is a normal Python script that uses Playwright (or any other library). eval-banana only cares about the exit code. Inside that script, you can read `os.environ["EVAL_BANANA_OUTPUT_DIR"]` to write screenshots or traces that end up alongside the check result.
