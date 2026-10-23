"""Scheme catalogue, graph traversal, jurisdiction-aware retrieval and rule evaluation."""
import json
import time

from flask import current_app

from . import i18n, metrics, profile, rules_engine
from .common import ApiError, audit
from .db import dumps, get_db, iso, new_id, row_to_dict


# ---------------------------------------------------------------- catalogue

def scheme_card(row, lang: str = "en", full: bool = False) -> dict:
    flags = json.loads(row["quality_flags_json"])
    card = {
        "scheme_id": row["scheme_id"],
        "name": row["name"],
        "state": row["state"],
        "level": row["level"],
        "department": row["department"],
        "categories": row["categories"],
        "beneficiaries": row["beneficiaries"],
        "brief_description": row["brief_description"],
        "source_url": row["source_url"],
        "freshness": {
            "imported_at": row["imported_at"],
            "retrieved_at": row["retrieved_at"],
            "verified_at": row["verified_at"],
            "review_status": row["review_status"],
            "confidence": row["confidence"],
            "label": "Catalogue entry — not verified against the official source"
            if not row["verified_at"] else f"Verified {row['verified_at']}",
        },
        "quality_flags": flags,
    }
    if full:
        card.update({
            "description": row["description"], "benefits": row["benefits"],
            "eligibility_text": row["eligibility_text"], "application_process": row["application_process"],
            "documents_text": row["documents_text"], "sources": json.loads(row["source_urls_json"]),
            "faqs": row["faqs"], "tags": row["tags"],
        })
    return card


def get_scheme(scheme_id: str) -> dict:
    row = get_db().execute("SELECT * FROM schemes WHERE scheme_id=?", (scheme_id,)).fetchone()
    if not row:
        raise ApiError("SCHEME_NOT_FOUND", "Scheme not found.", 404)
    card = scheme_card(row, full=True)
    rule = get_db().execute("SELECT rule_id, version, review_status, source_verified_at FROM rules WHERE scheme_id=? AND active=1",
                            (scheme_id,)).fetchone()
    card["rule"] = row_to_dict(rule)
    card["graph"] = related(scheme_id)
    return card


def search(q: str = "", state: str | None = None, level: str | None = None, category: str | None = None,
           beneficiary: str | None = None, include_central: bool = True, limit: int = 30, offset: int = 0,
           has_rule: bool = False) -> dict:
    where, args = [], []
    if state:
        if include_central:
            where.append("(s.state = ? OR s.level = 'Central')")
        else:
            where.append("s.state = ?")
        args.append(state)
    if level:
        where.append("s.level = ?")
        args.append(level)
    if category:
        where.append("s.categories LIKE ?")
        args.append(f"%{category}%")
    if beneficiary:
        where.append("s.beneficiaries LIKE ?")
        args.append(f"%{beneficiary}%")
    for word in [w for w in (q or "").lower().split() if len(w) > 1][:6]:
        where.append("s.search_text LIKE ?")
        args.append(f"%{word}%")
    if has_rule:
        where.append("r.rule_id IS NOT NULL")
    sql_where = ("WHERE " + " AND ".join(where)) if where else ""
    db = get_db()
    base = f"FROM schemes s LEFT JOIN rules r ON r.scheme_id = s.scheme_id AND r.active = 1 {sql_where}"
    total = db.execute(f"SELECT COUNT(*) {base}", args).fetchone()[0]
    rows = db.execute(
        f"SELECT s.*, r.rule_id AS rule_id {base} ORDER BY (r.rule_id IS NULL), s.level DESC, s.name LIMIT ? OFFSET ?",
        args + [limit, offset],
    ).fetchall()
    items = []
    for r in rows:
        c = scheme_card(r)
        c["has_reviewed_rule"] = r["rule_id"] is not None
        c["rule_id"] = r["rule_id"]
        items.append(c)
    return {"total": total, "items": items, "filters": {"q": q, "state": state, "level": level, "category": category}}


def facets() -> dict:
    db = get_db()
    states = [r[0] for r in db.execute("SELECT DISTINCT state FROM schemes WHERE state IS NOT NULL ORDER BY state")]
    cats = {}
    for (c,) in db.execute("SELECT categories FROM schemes"):
        for part in (c or "").split(","):
            p = part.strip()
            if p:
                cats[p] = cats.get(p, 0) + 1
    return {"states": states, "categories": sorted(cats, key=lambda k: -cats[k])[:25]}


def related(scheme_id: str) -> dict:
    """Graph traversal over the relational knowledge graph (kg_nodes / kg_edges)."""
    db = get_db()
    node = f"scheme:{scheme_id}"
    edges = db.execute(
        "SELECT e.rel, e.dst, n.node_type, n.label FROM kg_edges e JOIN kg_nodes n ON n.node_id = e.dst WHERE e.src=?",
        (node,),
    ).fetchall()
    out: dict[str, list] = {}
    for e in edges:
        out.setdefault(e["rel"], []).append({"node_id": e["dst"], "type": e["node_type"], "label": e["label"]})
    # Two-hop: other schemes in the same department and state (shows multi-hop relationships).
    siblings = db.execute(
        """SELECT DISTINCT s2.scheme_id, s2.name FROM kg_edges d1
           JOIN kg_edges d2 ON d2.dst = d1.dst AND d2.rel = 'ADMINISTERED_BY' AND d2.src != d1.src
           JOIN kg_edges st1 ON st1.src = d1.src AND st1.rel = 'APPLIES_IN'
           JOIN kg_edges st2 ON st2.src = d2.src AND st2.rel = 'APPLIES_IN' AND st2.dst = st1.dst
           JOIN schemes s2 ON 'scheme:' || s2.scheme_id = d2.src
           WHERE d1.src = ? AND d1.rel = 'ADMINISTERED_BY' LIMIT 8""",
        (node,),
    ).fetchall()
    out["SAME_DEPARTMENT_AND_STATE"] = [{"scheme_id": r["scheme_id"], "name": r["name"]} for r in siblings]
    return out


def graph_summary() -> dict:
    db = get_db()
    return {
        "nodes": {r[0]: r[1] for r in db.execute("SELECT node_type, COUNT(*) FROM kg_nodes GROUP BY node_type")},
        "edges": {r[0]: r[1] for r in db.execute("SELECT rel, COUNT(*) FROM kg_edges GROUP BY rel")},
    }


# ---------------------------------------------------------------- rules

def active_rules() -> list[dict]:
    db = get_db()
    rows = db.execute(
        """SELECT r.*, s.name AS scheme_name, s.source_url, s.imported_at, s.state AS scheme_state, s.level AS scheme_level
           FROM rules r JOIN schemes s ON s.scheme_id = r.scheme_id WHERE r.active = 1 ORDER BY r.rule_id"""
    ).fetchall()
    out = []
    for r in rows:
        rule = json.loads(r["rule_json"])
        meta = {
            "review_status": r["review_status"], "source_verified_at": r["source_verified_at"],
            "source_verified_by": r["source_verified_by"], "reviewed_at": r["reviewed_at"],
            "source_url": r["source_url"], "imported_at": r["imported_at"], "bundle_version": r["bundle_version"],
            "scheme_name": r["scheme_name"], "scheme_state": r["scheme_state"], "scheme_level": r["scheme_level"],
        }
        out.append({"rule": rule, "meta": meta})
    return out


def candidate_rules(state: str | None) -> list[dict]:
    """Jurisdiction resolution: central schemes always; state schemes only for the citizen's state."""
    out = []
    for item in active_rules():
        j = item["rule"]["jurisdiction"]
        if j.get("level") == "Central" or (state and j.get("state") == state):
            out.append(item)
    return out


def engine_facts(session_id: str) -> dict:
    return {a: {"fact_id": f["fact_id"], "value": f["value"], "confirmed": f["confirmed"]}
            for a, f in profile.current_facts(session_id).items()}


def doc_marks(session_id: str) -> dict:
    return {r["doc_key"]: r["status"] for r in get_db().execute(
        "SELECT doc_key, status FROM doc_marks WHERE session_id=?", (session_id,))}


def localize_result(res: dict, lang: str) -> dict:
    res = dict(res)
    res["outcome_label"] = i18n.t(i18n.OUTCOMES, res["outcome"], lang)
    res["evidence"] = [
        {**e, "label": i18n.doc_label(e["doc_key"], lang)[0], "purpose": i18n.doc_label(e["doc_key"], lang)[1],
         "status_label": i18n.t(i18n.DOC_STATUS, e["status"], lang)}
        for e in res["evidence"]
    ]
    res["missing_questions"] = [{"attribute": a, "text": i18n.t(i18n.QUESTIONS, a, lang)} for a in res["missing_facts"]]
    return res


def evaluate_session(session_id: str, *, require_confirmed=True, origin="online") -> dict:
    session = profile.get_session(session_id)
    lang = session["language"]
    pending = profile.unconfirmed_critical(session_id)
    if require_confirmed and pending:
        metrics.CONFIRMATION_BLOCKS.inc()
        raise ApiError("PROFILE_NEEDS_CONFIRMATION",
                       "Confirm or correct the highlighted details before checking schemes.", 409,
                       {"facts": [{"fact_id": f["fact_id"], "attribute": f["attribute"], "value": f["value"]} for f in pending]})
    facts = engine_facts(session_id)
    marks = doc_marks(session_id)
    state = facts.get("state", {}).get("value") if facts.get("state", {}).get("confirmed") else None
    candidates = candidate_rules(state)
    t0 = time.perf_counter()
    results = [rules_engine.evaluate(c["rule"], facts, marks, c["meta"]) for c in candidates]
    metrics.RULE_EVAL_SECONDS.observe(time.perf_counter() - t0)
    results = rules_engine.sort_results(results)
    metrics.EVALUATIONS.labels(origin).inc()
    for r in results:
        metrics.OUTCOMES.labels(r["rule_id"], r["outcome"]).inc()
    bundle_version = current_app.config["RULE_BUNDLE_VERSION"]

    db = get_db()
    prev = db.execute("SELECT results_json FROM evaluations WHERE session_id=? ORDER BY created_at DESC, rowid DESC LIMIT 1",
                      (session_id,)).fetchone()
    changes = []
    if prev:
        old = {r["scheme_id"]: r for r in json.loads(prev["results_json"])}
        new = {r["scheme_id"]: r for r in results}
        for sid in sorted(set(old) | set(new)):
            o, n = old.get(sid), new.get(sid)
            if (o and o["outcome"]) != (n and n["outcome"]):
                changes.append({"scheme_id": sid, "scheme_name": (n or o)["scheme_name"],
                                "before": o and o["outcome"], "after": n and n["outcome"]})

    eval_id = new_id("EVAL")
    fact_ids = sorted({f["fact_id"] for f in facts.values()})
    db.execute(
        "INSERT INTO evaluations(eval_id, session_id, bundle_version, created_at, fact_ids_json, results_json, origin) VALUES (?,?,?,?,?,?,?)",
        (eval_id, session_id, bundle_version, iso(), dumps(fact_ids), dumps(results), origin),
    )
    profile.set_workflow_state(session_id, "MATCH_RESULTS_READY")
    audit("eligibility.evaluate", session_id=session_id,
          details={"eval_id": eval_id, "bundle_version": bundle_version, "input_fact_ids": fact_ids,
                   "outcomes": {r["rule_id"]: r["outcome"] for r in results}})
    db.commit()
    return {
        "eval_id": eval_id,
        "bundle_version": bundle_version,
        "jurisdiction": {"state": state, "central_included": True,
                         "note": None if state else "State not confirmed — only central schemes were checked."},
        "input_fact_ids": fact_ids,
        "results": [localize_result(r, lang) for r in results],
        "changes_since_last": changes,
        "provisional_notice": "Results are preliminary screening only. They are not an approval or a guarantee of benefit.",
    }


def latest_evaluation(session_id: str) -> dict | None:
    row = get_db().execute("SELECT * FROM evaluations WHERE session_id=? ORDER BY created_at DESC, rowid DESC LIMIT 1",
                           (session_id,)).fetchone()
    if not row:
        return None
    return {"eval_id": row["eval_id"], "bundle_version": row["bundle_version"], "created_at": row["created_at"],
            "results": json.loads(row["results_json"]), "fact_ids": json.loads(row["fact_ids_json"])}


def set_doc_mark(session_id: str, doc_key: str, status: str, by: str = "citizen") -> dict:
    allowed = {"available", "missing", "expired", "unknown"} | ({"verified"} if by == "reviewer" else set())
    if status not in allowed:
        raise ApiError("INVALID_DOC_STATUS", "Citizens can mark available, missing, expired or unknown; only a reviewer can verify.", 422)
    if doc_key not in i18n.DOCUMENTS:
        raise ApiError("UNKNOWN_DOCUMENT", "Unknown document type.", 422)
    db = get_db()
    db.execute(
        "INSERT INTO doc_marks(session_id, doc_key, status, marked_by, updated_at) VALUES (?,?,?,?,?) "
        "ON CONFLICT(session_id, doc_key) DO UPDATE SET status=excluded.status, marked_by=excluded.marked_by, updated_at=excluded.updated_at",
        (session_id, doc_key, status, by, iso()),
    )
    audit("documents.mark", session_id=session_id, details={"doc_key": doc_key, "status": status, "by": by})
    db.commit()
    return doc_marks(session_id)


def document_guide(session_id: str) -> dict:
    """Union of evidence requirements across the latest non-mismatch results."""
    session = profile.get_session(session_id)
    lang = session["language"]
    ev = latest_evaluation(session_id)
    marks = doc_marks(session_id)
    docs: dict[str, dict] = {}
    for r in (ev["results"] if ev else []):
        if r["outcome"] == rules_engine.MISMATCH:
            continue
        for e in r["evidence"]:
            d = docs.setdefault(e["doc_key"], {"doc_key": e["doc_key"], "needed_for": []})
            d["needed_for"].append({"scheme_id": r["scheme_id"], "scheme_name": r["scheme_name"]})
    items = []
    for k, d in docs.items():
        label, purpose = i18n.doc_label(k, lang)
        status = marks.get(k, "unknown")
        items.append({**d, "label": label, "purpose": purpose, "status": status,
                      "status_label": i18n.t(i18n.DOC_STATUS, status, lang)})
    items.sort(key=lambda x: (-len(x["needed_for"]), x["label"]))
    return {"documents": items, "note": "Marking a document as available is your own declaration; it is not official verification."}
