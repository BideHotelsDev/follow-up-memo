"""Write the OpenAPI schema to a file (input for packages/shared-types)."""

import json
import sys
from pathlib import Path

from bide_followup.main import app

if __name__ == "__main__":
    out = Path(sys.argv[1])
    out.write_text(json.dumps(app.openapi(), indent=2) + "\n")
    print(f"wrote {out}")
