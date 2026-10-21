"""CLI: python -m anvaya.manage init | import | report | cleanup"""
import json
import sys

from . import create_app, ingest
from .db import connect, iso


def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "init"
    app = create_app()
    cfg = app.config
    conn = connect(cfg["DB_PATH"])
    if cmd in ("init", "import"):
        res = ingest.bootstrap(conn, cfg["DATASET_CSV"], cfg["GOLDEN_RULES"], cfg["RULE_BUNDLE_VERSION"])
        cat = res["catalogue"]
        print(f"catalogue: {cat['rows']} rows, {cat['distinct_names']} distinct names, "
              f"{len(cat['states'])} jurisdictions, sha256={cat['sha256'][:16]}… (skipped={cat['skipped']})")
        print("quality flags:", json.dumps(cat["flag_counts"]))
        for r in res["rules"]["rules"]:
            mark = "OK " if not r["problems"] else "!! "
            print(f"  {mark}{r['rule_id']:<28} {r['review_status']:<14} {'; '.join(r['problems'])}")
        return 0
    if cmd == "report":
        row = conn.execute("SELECT report_json FROM source_artifacts ORDER BY imported_at DESC LIMIT 1").fetchone()
        print(json.dumps(json.loads(row[0]), indent=2, ensure_ascii=False) if row else "no import yet")
        return 0
    if cmd == "cleanup":
        n = conn.execute("UPDATE sessions SET ended_at=? WHERE ended_at IS NULL AND expires_at < ?", (iso(), iso())).rowcount
        conn.commit()
        print(f"expired {n} sessions")
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
