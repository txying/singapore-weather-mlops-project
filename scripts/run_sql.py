from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.common.config import load_env  # noqa: E402


PLACEHOLDER_RE = re.compile(r"\$\{([A-Z0-9_]+)\}")


def render_sql(sql: str, values: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in values:
            raise RuntimeError(f"Missing value for SQL placeholder: {key}")
        return values[key]

    return PLACEHOLDER_RE.sub(replace, sql)


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a SQL file with .env values and run it with bq.")
    parser.add_argument("sql_file", type=Path, help="Path to the SQL file containing ${VAR} placeholders.")
    parser.add_argument("--env-file", type=Path, default=PROJECT_ROOT / ".env")
    parser.add_argument("--dry-run", action="store_true", help="Print rendered SQL without executing it.")
    args = parser.parse_args()

    values = load_env(args.env_file)
    sql = args.sql_file.read_text(encoding="utf-8")
    rendered_sql = render_sql(sql, values)

    if args.dry_run:
        print(rendered_sql)
        return 0

    with tempfile.NamedTemporaryFile("w", suffix=".sql", encoding="utf-8") as rendered_file:
        rendered_file.write(rendered_sql)
        rendered_file.flush()
        with Path(rendered_file.name).open("r", encoding="utf-8") as stdin:
            result = subprocess.run(
                ["bq", "query", "--use_legacy_sql=false"],
                stdin=stdin,
                check=False,
            )
        return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
