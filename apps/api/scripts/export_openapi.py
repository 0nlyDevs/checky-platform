"""Write the OpenAPI schema to packages/shared without starting a server."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import api

out = Path(__file__).resolve().parents[3] / "packages" / "shared" / "openapi.json"
out.write_text(json.dumps(api.openapi(), indent=2, ensure_ascii=False) + "\n")
print(f"wrote {out}")
