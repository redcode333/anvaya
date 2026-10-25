"""CLI: python -m anvaya.manage init | import | report | cleanup | seed-staff | eval-extraction [--no-llm] [--json]
                          | prerender-audio [--max-count N] [--concurrency N] [--per-minute N] [--dry-run]"""
import json
import sys
import time

from . import create_app, ingest
from .db import connect, dispose, iso


def _opt(argv: list[str], name: str, default: int) -> int:
    return int(argv[argv.index(name) + 1]) if name in argv else default


def _record_staff_change(app, res: dict, role: str) -> None:
    """Auth audit for seed-staff: a role change, and a password set again (existing sessions are signed out)."""
    from . import auth
    from .db import get_db
    if not res.get("user_id"):
        return
    with app.app_context():
        if res["previous_role"] != role:
            auth.record("role_changed", "system", "system",
                        {"user_id": res["user_id"], "from": res["previous_role"], "to": role})
        if res["action"] == "updated":
            auth.revoke_sessions(res["user_id"], "password_changed")
            auth.record("password_changed", "system", "system", {"user_id": res["user_id"], "global_sign_out": True})
        get_db().commit()


def main(argv: list[str]) -> int:
    app = create_app()
    conn = connect(app.config)
    try:
        return _run(argv, app, conn)
    finally:
        conn.close()
        dispose(app.config)


def _run(argv: list[str], app, conn) -> int:
    cmd = argv[0] if argv else "init"
    cfg = app.config
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
        from .accounts import purge_expired
        from .voice import purge_audio
        a = purge_audio(conn, cfg["SESSION_TTL_HOURS"])
        print(f"expired {n} sessions; removed {a} cached audio clips older than {cfg['SESSION_TTL_HOURS']} h")
        with app.app_context():
            r = purge_expired(conn, cfg)
        print(f"retention: deleted {r['unsaved_sessions']} unsaved sessions older than {cfg['UNSAVED_RETENTION_HOURS']} h,"
              f" {r['unsaved_citizens']} unsaved citizens, {r['inactive_passports']} passports inactive for"
              f" {cfg['PASSPORT_RETENTION_DAYS']} days, {r['auth_users_deleted']} Supabase Auth users")
        return 0
    if cmd == "seed-staff":
        # Staff roles live in Supabase app_metadata, which only the server (secret key) can set. Prints emails'
        # roles and actions only, never passwords.
        import os
        from .auth import upsert_staff
        from .config import STAFF_ROLES
        if not (cfg["SUPABASE_URL"] and cfg["SUPABASE_SECRET_KEY"]):
            print("SUPABASE_URL and SUPABASE_SECRET_KEY must be set")
            return 1
        missing = 0
        for role, (email_var, password_var) in STAFF_ROLES.items():
            email, password = os.environ.get(email_var, "").strip(), os.environ.get(password_var, "")
            if not email or not password:
                print(f"  {role:<9} skipped: set {email_var} and {password_var}")
                missing += 1
                continue
            if len(password) < 8:
                print(f"  {role:<9} skipped: {password_var} must be at least 8 characters")
                missing += 1
                continue
            res = upsert_staff(cfg, email, password, role)
            print(f"  {role:<9} {res['action']}")
            _record_staff_change(app, res, role)
        return 1 if missing else 0
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
            pushed = evaluate.push_to_langfuse(use_llm="--no-llm" not in argv) if cfg["LANGFUSE_TRACE_EVAL"] else []
        print(json.dumps(res, indent=2, ensure_ascii=False) if "--json" in argv else evaluate.report(res))
        for r in pushed:
            print(f"langfuse experiment {r['run']}: {r['items']} items, wrong facts {r.get('wrong_facts_reaching_confirmation')}"
                  f" (high-impact {r.get('wrong_high_impact_facts')}), mean recall {r.get('mean_recall')}"
                  + (f"  {r['url']}" if r.get("url") else ""))
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
