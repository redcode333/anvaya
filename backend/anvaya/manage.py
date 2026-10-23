"""CLI: python -m anvaya.manage init | import | report | cleanup | eval-extraction [--no-llm] [--json]
                          | prerender-audio [--max-count N] [--concurrency N] [--per-minute N] [--dry-run]"""
import json
import sys
import time

from . import create_app, ingest
from .db import connect, iso


def _opt(argv: list[str], name: str, default: int) -> int:
    return int(argv[argv.index(name) + 1]) if name in argv else default


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
        from .voice import purge_audio
        a = purge_audio(conn, cfg["SESSION_TTL_HOURS"])
        print(f"expired {n} sessions; removed {a} cached audio clips older than {cfg['SESSION_TTL_HOURS']} h")
        return 0
    if cmd == "prerender-audio":
        from . import prerender, voice
        with app.app_context():
            if not conn.execute("SELECT COUNT(*) FROM rules WHERE active=1").fetchone()[0]:
                print("no rules loaded: run `python -m anvaya.manage init` first")
                return 1
            items = prerender.texts(max_count=_opt(argv, "--max-count", 4))
            kinds = {}
            for _, lang, kind in items:
                kinds[f"{kind}/{lang}"] = kinds.get(f"{kind}/{lang}", 0) + 1
            print(f"{len(items)} fixed prompts: " + ", ".join(f"{k}={v}" for k, v in sorted(kinds.items())))
            if "--dry-run" in argv:
                return 0
            if not voice.configured():
                print("VerbX is not configured (VERBX_BASE_URL / VERBX_API_KEY): nothing synthesized")
                return 1
            t0, done = time.perf_counter(), []

            def progress(row):
                done.append(row)
                ms = f"{row['ms']:>6} ms" if row["ms"] is not None else "     -   "
                print(f"  [{len(done):>3}/{len(items)}] {row['language']} {row['result']:<12} {ms}  {len(row['text']):>3} chars")
            rows = voice.prerender([(t, lang) for t, lang, _ in items],
                                   concurrency=_opt(argv, "--concurrency", 3),
                                   per_minute=_opt(argv, "--per-minute", 40), on_result=progress)
            synth = sorted(r["ms"] for r in rows if r["result"] == "synthesized")
            errors = [r for r in rows if r["result"].startswith("error")]
            print(f"done in {time.perf_counter() - t0:.1f} s: {len(synth)} synthesized, "
                  f"{sum(r['result'] == 'cached' for r in rows)} already cached, {len(errors)} failed")
            if synth:
                print(f"VerbX TTS latency ms: median {synth[len(synth) // 2]}, max {synth[-1]}")
            print(f"cache: {voice.cache_stats()}")
            return 1 if errors else 0
    if cmd == "eval-extraction":
        from .llm import evaluate
        with app.app_context():
            res = evaluate.run(use_llm="--no-llm" not in argv)
        print(json.dumps(res, indent=2, ensure_ascii=False) if "--json" in argv else evaluate.report(res))
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
