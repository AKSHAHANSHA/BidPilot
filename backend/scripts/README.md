# Scripts

| Script | Purpose | Phase |
|---|---|---|
| `export_openapi.py` | Writes `artifacts/openapi.json` for frontend type generation | 0 |
| `seed_demo.py` | Creates the demo user, company profile, and evidence items | 2 |
| `evaluate_pipeline.py` | Scores extraction against the gold sample set and saves a JSON report | 11 |

Scripts are thin entry points. Logic lives in `app/services` so it can be tested without a
subprocess.
