# sps-hub

[![CI](https://github.com/swimusa-dev/sps-hub/actions/workflows/ci.yml/badge.svg)](https://github.com/swimusa-dev/sps-hub/actions/workflows/ci.yml)

Files reports emailed to `sps-analytics@swimusa.com` into the Swim USA CompanyHub SharePoint library, organized `year / retailer / report family / brand` and named so any report is findable in seconds.

## Layout

| Path | What it is |
| --- | --- |
| `src/sps_filing/` | The parser and filer. `plan_filing` is pure: no I/O, fully testable. |
| `function_app.py` | Azure Functions triggers: timer, backfill, parse preview. |
| `data/sps_filing_map_seed.csv` | Seed for the SharePoint `SPS Filing Map` list, and the test fixture. |
| `tools/` | Regenerates the seed. |
| `tests/` | 43 tests, including the nine-subject acceptance trace table. |
| `docs/` | Design guide and Azure deployment guide. |

## Getting started

```bash
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
pytest
```

No Azure resources or tenant access are needed to run the tests.

CI runs the same steps on every pull request: the test suite on Python 3.11, an
import check over the Azure-facing modules, and a check that
`data/sps_filing_map_seed.csv` still matches its generator.

## Docs

- [Architecture decisions](docs/architecture-decisions.md): why the system is shaped this way, and what was considered and rejected. Start here if you are wondering why something is the way it is.
- [Design guide](docs/sps-analytics-filing-flow-build-guide.md): folder structure, filename grammar, the parsing rules and why each exists, the data-quality defects in the SPS feed that the parser tolerates.
- [Azure Function build and deployment guide](docs/azure-function-build-guide.md): identity setup, app settings, go-live sequence, operations.
