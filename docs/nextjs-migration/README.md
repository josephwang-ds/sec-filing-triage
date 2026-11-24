# Company Lens v2 — Next.js migration

The front end is being moved from a 3,000-line Python HTML renderer to a
Next.js app under `apps/lens-web`. The Python research engine keeps every
number; the new front end reads its output through a validated contract and
never recomputes a research figure.

| Document | What it covers |
| --- | --- |
| [BASELINE.md](BASELINE.md) | The production system as found, and the contracts it publishes |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Old and new architecture, and the boundary between them |
| [MIGRATION_MATRIX.md](MIGRATION_MATRIX.md) | Page by page and feature by feature |
| [I18N_AUDIT.md](I18N_AUDIT.md) | Bilingual coverage, and what is deliberately not translated |
| [DATA_PARITY.md](DATA_PARITY.md) | Old page against new page, value by value |
| [QA_REPORT.md](QA_REPORT.md) | Test output, and the known limits of this run |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Preview deployment, production cutover and rollback |
