# Verso build/verify loop.
#
#   make corpus   build labeled adversarial PDFs from corpus/manifest.yaml
#   make eval     run the detector over the corpus, write eval/results.json
#   make check    determinism gate: scan twice, assert identical output hash
#   make lint     enforce architectural invariants (no LLM imports in detect/)
#   make test     unit tests
#
# PY resolves to the project virtualenv if present, else system python3.

PY := $(shell [ -x .venv/bin/python ] && echo .venv/bin/python || echo python3)

.PHONY: install corpus eval check lint test demo web clean all

install:
	$(PY) -m pip install -e .

corpus:
	$(PY) -m corpus.build

eval:
	$(PY) -m eval.run

check:
	$(PY) -m eval.check

lint:
	$(PY) tools/lint_no_llm.py

test:
	$(PY) -m pytest -q tests

demo:
	$(PY) -m eval.run
	@echo "See eval/results.json and docs/*.png"

web:
	$(PY) -m webapp

foxit:
	./integrations/run_foxit_gateway.sh

all: corpus eval check lint

clean:
	rm -rf corpus/build eval/results.json
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
