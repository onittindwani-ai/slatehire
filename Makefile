PY=.venv/bin/python

.PHONY: install test seed-check doctor check-env api worker web e2e counts docs-check

install:
	@if command -v uv >/dev/null 2>&1; then \
	  uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -e packages/core-py -e "apps/api[dev]"; \
	elif command -v python3.12 >/dev/null 2>&1; then \
	  python3.12 -m venv .venv && .venv/bin/pip install -e packages/core-py -e "apps/api[dev]"; \
	else \
	  echo "Neither uv nor python3.12 found. Install uv (https://docs.astral.sh/uv/) or Python 3.12, then run make install again."; exit 1; \
	fi
	@command -v pnpm >/dev/null 2>&1 || { echo "pnpm not found. Run: corepack enable   (or: npm i -g pnpm)"; exit 1; }
	pnpm install

test:
	$(PY) -m pytest

seed-check:
	$(PY) tools/eval_redaction.py
	$(PY) tools/eval_scoring.py
	$(PY) tools/score_tools.py --check

doctor:
	$(PY) tools/doctor.py

check-env:
	python3 tools/check_env.py

api:
	$(PY) -m uvicorn slatehire.api.app:app_from_env --factory --port 8000 --proxy-headers

worker:
	$(PY) -m slatehire.worker

web:
	pnpm build && pnpm --filter web start

e2e:
	pnpm e2e

counts:
	$(PY) tools/make_counts.py

docs-check:
	$(PY) tools/check_docs.py
