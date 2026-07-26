"""Export the OpenAPI document to `artifacts/openapi.json`.

The frontend generates its types from this file rather than duplicating backend interfaces
by hand (`docs/04_API_AND_DATA_MODEL.md` §7), so it is a build artifact, not documentation
prose. Committing it also makes contract changes visible in review.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import Settings, get_settings  # noqa: E402
from app.main import create_app  # noqa: E402

OUTPUT_PATH = BACKEND_ROOT / "artifacts" / "openapi.json"


def build_schema() -> dict[str, object]:
    # Production disables the schema endpoint; export from a non-production copy so the
    # command works regardless of the local APP_ENV.
    settings: Settings = get_settings().model_copy(update={"app_env": "development"})
    return create_app(settings).openapi()


def main() -> int:
    schema = build_schema()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    paths = schema.get("paths", {})
    assert isinstance(paths, dict)  # noqa: S101 - guards the count printed below
    print(f"Wrote {OUTPUT_PATH.relative_to(BACKEND_ROOT)} ({len(paths)} paths)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
