# Resolve the interpreter once, rather than making every user discover it.
#
# The project's own virtualenv comes first. It sits in the source tree, it is the
# one the dependencies are installed into, and forgetting to activate a shell is
# not a reason for the build to fail with a version error about a system Python
# nobody meant to use. After that: python3 (macOS ships no bare `python`), then
# python (some Linux images are the other way round). PYTHON=... overrides all of it.
PYTHON ?= $(shell   test -x .venv/bin/python && echo .venv/bin/python ||   command -v python3 2>/dev/null ||   command -v python 2>/dev/null)

# Put src/ on the path for every target, rather than trusting the editable
# install. `pip install -e .` writes a .pth file, and on macOS an iCloud-synced
# checkout gets UF_HIDDEN re-applied to everything under .venv/ -- CPython
# skips hidden .pth files *silently*, so the install reports success and every
# target then fails with ModuleNotFoundError. Exporting the path costs nothing
# when the install is fine and removes a failure mode that looks like a bug in
# the project.
export PYTHONPATH := $(CURDIR)/src$(if $(PYTHONPATH),:$(PYTHONPATH))

.PHONY: help install lock install-locked demo earnings-calendar ladder-chart overview-page research-page self-relative-evidence text-cache volatility-cache volatility-evidence quick audit doctor test lint ingest refresh-filings refresh-fundamentals refresh-headlines refresh-all vercel-bundle vercel-deploy run company company-featured company-pages evidence nlp-eval llm-eval llm-eval-provider-dry-run llm-eval-openai-dry-run clean

help:
	@echo "make install   install the package and dev dependencies"
	@echo "make lock      pin the current environment into requirements.lock"
	@echo "make install-locked  install the pinned environment instead of resolving"
	@echo "make demo      synthetic world -> pipeline -> data/build/report.html"
	@echo "make quick     the same, smaller and without the leakage study"
	@echo "make universe  resolve the demo ticker list to CIKs (needs network)"
	@echo "make doctor    check that a real ingest would work, before starting one"
	@echo "make audit     run the leakage checks; non-zero exit on any failure"
	@echo "make test      run the test suite"
	@echo "make ingest    pull real EDGAR filings and prices (needs network)"
	@echo "make refresh-filings  incrementally check SEC for new 8-Ks (needs network)"
	@echo "make refresh-fundamentals  refresh the AAPL annual Company Facts pilot"
	@echo "make refresh-headlines  refresh bounded Finnhub headline metadata"
	@echo "make refresh-all  locked SEC + market refresh and static page rebuild"
	@echo "make vercel-bundle  package public HTML as Vercel prebuilt output"
	@echo "make vercel-deploy  deploy the prebuilt frontend to Vercel production"
	@echo "make run       run the pipeline over whatever make ingest produced"
	@echo "make company   build an AAPL Company Lens snapshot from local data"
	@echo "make company-featured  quickly build AAPL/MSFT/NVDA pages"
	@echo "make company-pages  build all locally available company pages"
	@echo "make earnings-calendar  expected reporting dates for the universe"
	@echo "make overview-page  the project in plain words, for a non-specialist"
	@echo "make ladder-chart   regenerate the README figure from evidence/"
	@echo "make research-page  the audited findings, generated from evidence/"
	@echo "make self-relative-evidence  issuer-relative percentiles, calibration, policy"
	@echo "make text-cache    encode filings with FinBERT (needs the [nlp] extra)"
	@echo "make volatility-evidence  score the 20-session volatility forecasters"
	@echo "make volatility-cache     Chronos-2 forecasts (needs the [ts] extra)"
	@echo "make evidence  export real-run metrics, intervals and studies (no raw data)"
	@echo "make nlp-eval  evaluate prior-filing change detection on labeled spans"
	@echo "make llm-eval  score frozen bilingual grounded-explanation fixtures"
	@echo "make llm-eval-provider-dry-run PROVIDER=qwen  inspect a provider run"
	@echo "make llm-eval-openai-dry-run  inspect paid benchmark scope without an API call"
	@echo
	@echo "using PYTHON=$(PYTHON)"

check-python:
	@test -n "$(PYTHON)" || { \
	  echo "No python3 found on PATH."; \
	  echo "  macOS:  brew install python@3.12"; \
	  echo "  Ubuntu: sudo apt install python3 python3-venv"; \
	  exit 1; }
	@$(PYTHON) -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' || { \
	  echo "Python 3.11+ required; $(PYTHON) is $$($(PYTHON) -V 2>&1)."; \
	  echo; \
	  echo "macOS ships 3.9 with the Xcode command line tools, and a venv built"; \
	  echo "from it inherits both the old interpreter and a pip too old to install"; \
	  echo "this project at all. Build the venv from a newer interpreter:"; \
	  echo; \
	  echo "  brew install python@3.12"; \
	  echo "  rm -rf .venv && python3.12 -m venv .venv"; \
	  echo "  source .venv/bin/activate"; \
	  echo "  make install"; \
	  exit 1; }

install: check-python
	@# pip older than 21.3 cannot do an editable install of a project that has
	@# only a pyproject.toml (PEP 660), and fails claiming setup.py is missing --
	@# which sends you looking for the wrong problem entirely. Upgrade first.
	$(PYTHON) -m pip install --upgrade pip setuptools wheel
	$(PYTHON) -m pip install -e ".[dev]"

# Reproduce the environment a committed result was produced on, rather than
# resolving `>=` floors to whatever is newest today. Use this before comparing
# your numbers with the ones in evidence/real_run.
install-locked: check-python
	$(PYTHON) -m pip install --upgrade pip setuptools wheel
	$(PYTHON) -m pip install -r requirements.lock
	$(PYTHON) -m pip install -e . --no-deps

# Run after deliberately upgrading something. Re-export the evidence in the same
# commit: manifest.json records the environment each result came from, so a lock
# bump without a re-export leaves the two disagreeing.
lock: check-python
	@# Built into a temporary file and moved into place. Redirecting straight to
	@# requirements.lock truncates it before the header is read back out of it,
	@# which silently loses everything above the generated line.
	@$(PYTHON) -m pip freeze --exclude-editable \
	  | grep -v '^filing-triage==' | sort > .lock.body
	@sed -n '/^# Python /q;p' requirements.lock > .lock.head
	@{ \
	  cat .lock.head; \
	  echo "# Python $$($(PYTHON) -c 'import sys;print(".".join(map(str,sys.version_info[:3])))') · generated $$(date -u +%Y-%m-%d)"; \
	  echo; \
	  cat .lock.body; \
	} > .lock.new
	@mv .lock.new requirements.lock
	@rm -f .lock.body .lock.head
	@echo "requirements.lock updated ($$(grep -c '==' requirements.lock) packages)"

# FORCE=1 reaches the CLI's --force, which is the only way past the guard that
# stops a synthetic world overwriting a real EDGAR build in data/build.
demo: check-python
	$(PYTHON) -m filing_triage.cli demo --issuers 300 $(if $(FORCE),--force)

quick: check-python
	$(PYTHON) -m filing_triage.cli demo --issuers 80 --quick $(if $(FORCE),--force)

doctor: check-python
	$(PYTHON) -m filing_triage.cli doctor

audit: check-python
	$(PYTHON) -m filing_triage.cli audit

test: check-python
	$(PYTHON) -m pytest

lint: check-python
	$(PYTHON) -m ruff check src tests scripts

universe: check-python
	@test -n "$$EDGAR_USER_AGENT" || { \
	  echo 'export EDGAR_USER_AGENT="Your Name you@example.com"'; exit 1; }
	$(PYTHON) scripts/build_demo_universe.py --out data/build/universe.csv

ingest: check-python
	@test -n "$$EDGAR_USER_AGENT" || { \
	  echo 'EDGAR_USER_AGENT is not set. The SEC requires an identifying'; \
	  echo 'User-Agent with a real name and email:'; \
	  echo; \
	  echo '  export EDGAR_USER_AGENT="Your Name you@example.com"'; \
	  exit 1; }
	$(PYTHON) -m filing_triage.cli ingest

refresh-filings: check-python
	@test -n "$$EDGAR_USER_AGENT" || { \
	  echo 'EDGAR_USER_AGENT is not set. The SEC requires a real name and email.'; \
	  echo '  export EDGAR_USER_AGENT="Your Name you@example.com"'; exit 1; }
	PYTHONPATH=src $(PYTHON) scripts/refresh_filings.py
	$(MAKE) company-pages

refresh-fundamentals: check-python
	@test -n "$$EDGAR_USER_AGENT" || { \
	  echo 'EDGAR_USER_AGENT is not set. The SEC requires a real name and email.'; \
	  echo '  export EDGAR_USER_AGENT="Your Name you@example.com"'; exit 1; }
	PYTHONPATH=src $(PYTHON) scripts/refresh_fundamentals.py --tickers AAPL

refresh-headlines: check-python
	@test -n "$$FINNHUB_API_KEY" || { \
	  echo 'FINNHUB_API_KEY is not set. Add it to .env and source the file.'; exit 1; }
	PYTHONPATH=src $(PYTHON) scripts/refresh_headlines.py

refresh-all: check-python
	@test -n "$$EDGAR_USER_AGENT" || { \
	  echo 'EDGAR_USER_AGENT is not set. The SEC requires a real name and email.'; \
	  echo '  export EDGAR_USER_AGENT="Your Name you@example.com"'; exit 1; }
	scripts/run_scheduled_refresh.sh

# One pass of FinBERT over the filing corpus, cached by model, revision and
# text hash. Optional: `pip install -e '.[nlp]'` first. Nothing else needs it.
text-cache: check-python
	PYTHONPATH=src $(PYTHON) scripts/build_text_cache.py

# One zero-shot pass of Chronos-2 over every filing's volatility history, cached
# by model, revision and context digest. Optional: `pip install -e '.[ts]'`.
# The baselines it is scored against need nothing.
volatility-cache: check-python
	PYTHONPATH=src $(PYTHON) scripts/build_volatility_cache.py

# Scores the volatility forecasters against each other and decides, from the
# numbers, whether any of them is calibrated enough to put on a card.
volatility-evidence: check-python
	PYTHONPATH=src $(PYTHON) scripts/export_volatility_evidence.py

# The issuer-relative layer: self-benchmarking percentiles, the calibrated
# impact probability and the reading policy, with the studies behind each of the
# three settings that were assumed rather than derived.
self-relative-evidence: check-python
	PYTHONPATH=src $(PYTHON) scripts/export_self_relative_evidence.py

# The filing-triage findings as a page on the live site, generated from the
# committed evidence so it cannot drift from it, plus the full generated report
# beside it for detail. Both land in company_pages, so `make vercel-bundle`
# carries them with everything else.
# The project in ordinary words, for a reader with no finance or ML background.
# Generated from the same evidence package as everything else, because the
# hand-written write-up this replaces had drifted three numbers out of date.
# The README's one picture: the leakage ladder, drawn from the same evidence the
# pages read, so it cannot drift into showing a number the code has moved past.
ladder-chart: check-python
	PYTHONPATH=src $(PYTHON) scripts/build_ladder_chart.py

overview-page: check-python
	PYTHONPATH=src $(PYTHON) scripts/build_overview_page.py

research-page: check-python
	PYTHONPATH=src $(PYTHON) scripts/build_research_page.py
	@test -f data/build/report.html && cp data/build/report.html \
	  data/build/company_pages/report.html \
	  && echo "full report -> data/build/company_pages/report.html" \
	  || echo "no data/build/report.html yet; run 'make run' for the full report"

# Expected reporting dates for the whole universe, inferred from each issuer's
# own Item 2.02 cadence. Written into company_pages so `make vercel-bundle`
# carries it to the live site with everything else.
earnings-calendar: check-python
	PYTHONPATH=src $(PYTHON) scripts/build_earnings_calendar.py

vercel-bundle: check-python
	PYTHONPATH=src $(PYTHON) scripts/build_vercel_output.py

vercel-deploy: vercel-bundle
	scripts/deploy_vercel_frontend.sh

run: check-python
	$(PYTHON) -m filing_triage.cli run

company: check-python
	PYTHONPATH=src $(PYTHON) -m company_lens.cli AAPL

company-featured: check-python
	PYTHONPATH=src $(PYTHON) scripts/build_company_pages.py --tickers AAPL MSFT NVDA --out data/build/company_featured

company-pages: check-python
	PYTHONPATH=src $(PYTHON) scripts/build_company_pages.py

evidence: check-python
	PYTHONPATH=src $(PYTHON) scripts/export_real_evidence.py

nlp-eval: check-python
	PYTHONPATH=src $(PYTHON) scripts/evaluate_filing_changes.py

llm-eval: check-python
	PYTHONPATH=src $(PYTHON) scripts/evaluate_grounded_llm.py

llm-eval-provider-dry-run: check-python
	PYTHONPATH=src $(PYTHON) scripts/run_llm_eval.py --provider $(or $(PROVIDER),openai) $(if $(MODEL),--model $(MODEL),) --dry-run

llm-eval-openai-dry-run: check-python
	PYTHONPATH=src $(PYTHON) scripts/run_llm_eval.py --provider openai --dry-run

clean:
	rm -rf data/build .pytest_cache .ruff_cache
	find . -name __pycache__ -type d -exec rm -rf {} +
