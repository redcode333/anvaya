"""Dataset import: immutable source artifact + normalized catalogue + graph edges + rules.

Run via `python -m anvaya.manage init` (see manage.py).
"""
import csv
import hashlib
import html
import json
import re
import sqlite3
import sys
from pathlib import Path

from werkzeug.security import generate_password_hash

from .db import dumps, init_schema, iso, new_id

csv.field_size_limit(min(sys.maxsize, 2**31 - 1))

URL_RE = re.compile(r"https?://\S+")
LIST_MARKER_RE = re.compile(r"(^|\n)\s*(\d+[.)]|-|•|\*)\s+")
WS_RE = re.compile(r"[ \t\r\f\v]+")

DEMO_USERS = [
    ("reviewer", "reviewer123", "reviewer", "Demo Reviewer"),
    ("operator", "operator123", "operator", "Demo Kiosk Operator"),
    ("admin", "admin123", "admin", "Demo Data Steward"),
]


def clean_text(s: str | None) -> str:
    if not s:
        return ""
    s = html.unescape(s)
    s = s.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
    s = WS_RE.sub(" ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def normalize_for_match(s: str) -> str:
    s = clean_text(s)
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", s).strip().lower()


def parse_source_urls(raw: str) -> list[dict]:
    out = []
    for line in clean_text(raw).split("\n"):
        line = line.strip()
        if not line:
            continue
        m = URL_RE.search(line)
        if not m:
            out.append({"label": line, "url": None})
            continue
        label = line[: m.start()].strip().rstrip(":").strip() or "Source"
        out.append({"label": label, "url": m.group(0).rstrip(".,;)")})
    return out


def normalize_level(level_raw: str, state_raw: str) -> tuple[str, str | None]:
    lv = (level_raw or "").strip().lower()
    st = (state_raw or "").strip()
    if lv == "central" or st == "Pan India":
        return "Central", None
    return "State", st or None


def quality_flags(row: dict, urls: list[dict], level: str) -> list[str]:
    flags = []
    if not urls or not any(u["url"] for u in urls):
        flags.append("no_source_url")
    elif any(u["url"] is None for u in urls):
        flags.append("source_line_without_url")
    docs = clean_text(row.get("documents"))
    if not docs:
        flags.append("documents_empty")
    elif not LIST_MARKER_RE.search(docs) and "\n" not in docs and len(docs) > 120:
        flags.append("documents_not_a_list")
    if not clean_text(row.get("eligibility_criteria")):
        flags.append("eligibility_empty")
    if "&" in (row.get("eligibility_criteria") or "") and "&amp;" in row["eligibility_criteria"]:
        flags.append("html_entities_normalized")
    if level == "Central" and row.get("state") not in ("Pan India", ""):
        flags.append("level_state_conflict")
    if level == "State" and (row.get("level") or "").strip().lower() == "central":
        flags.append("level_state_conflict")
    if not (row.get("faqs") or "").strip():
        flags.append("faqs_missing")
    return flags


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _node(conn, node_id, node_type, label):
    conn.execute(
        "INSERT OR IGNORE INTO kg_nodes(node_id, node_type, label) VALUES (?,?,?)",
        (node_id, node_type, label),
    )


def _edge(conn, src, rel, dst):
    conn.execute("INSERT OR IGNORE INTO kg_edges(src, rel, dst) VALUES (?,?,?)", (src, rel, dst))


def import_catalogue(conn: sqlite3.Connection, csv_path: str) -> dict:
    path = Path(csv_path)
    digest = sha256_file(path)
    existing = conn.execute(
        "SELECT artifact_id, report_json FROM source_artifacts WHERE sha256=?", (digest,)
    ).fetchone()
    if existing:
        return {"artifact_id": existing["artifact_id"], "skipped": True, **json.loads(existing["report_json"])}

    imported_at = iso()
    artifact_id = new_id("SRCART")
    seen_names: dict[str, str] = {}
    report = {
        "filename": path.name,
        "sha256": digest,
        "rows": 0,
        "distinct_names": 0,
        "states": {},
        "levels": {},
        "flag_counts": {},
        "duplicate_ids": [],
        "duplicate_names": [],
    }
    seen_ids = set()

    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            report["rows"] += 1
            sid = row["scheme_id"].strip()
            if sid in seen_ids:
                report["duplicate_ids"].append(sid)
                continue
            seen_ids.add(sid)
            name = clean_text(row["scheme_name"])
            key = name.lower()
            if key in seen_names:
                report["duplicate_names"].append(name)
            seen_names[key] = sid

            level, state = normalize_level(row.get("level", ""), row.get("state", ""))
            urls = parse_source_urls(row.get("source_url", ""))
            flags = quality_flags(row, urls, level)
            primary = next((u["url"] for u in urls if u["url"]), None)
            report["states"][state or "Central (Pan India)"] = report["states"].get(state or "Central (Pan India)", 0) + 1
            report["levels"][level] = report["levels"].get(level, 0) + 1
            for fl in flags:
                report["flag_counts"][fl] = report["flag_counts"].get(fl, 0) + 1

            search_text = " ".join(
                clean_text(row.get(k, "")) for k in ("scheme_name", "short_title", "tags", "categories", "subcategories", "brief_description")
            ).lower()

            conn.execute(
                """INSERT INTO schemes(scheme_id, slug, name, short_title, state_raw, state, level_raw, level,
                    department, categories, subcategories, tags, beneficiaries, brief_description, description,
                    benefits, eligibility_text, application_process, documents_text, source_urls_json, source_url,
                    faqs, source_artifact_id, imported_at, retrieved_at, verified_at, review_status, confidence,
                    quality_flags_json, search_text)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    sid, row.get("slug"), name, clean_text(row.get("short_title")),
                    row.get("state"), state, row.get("level"), level,
                    clean_text(row.get("department")), clean_text(row.get("categories")),
                    clean_text(row.get("subcategories")), clean_text(row.get("tags")),
                    clean_text(row.get("target_beneficiaries")), clean_text(row.get("brief_description")),
                    clean_text(row.get("description")), clean_text(row.get("benefits")),
                    clean_text(row.get("eligibility_criteria")), clean_text(row.get("application_process")),
                    clean_text(row.get("documents")), dumps(urls), primary, clean_text(row.get("faqs")),
                    artifact_id, imported_at, None, None,
                    "unreviewed_catalogue", "low", dumps(flags), search_text,
                ),
            )

            scheme_node = f"scheme:{sid}"
            _node(conn, scheme_node, "Scheme", name)
            state_node = f"state:{state or 'India'}"
            _node(conn, state_node, "State" if state else "Country", state or "India (Central)")
            _edge(conn, scheme_node, "APPLIES_IN", state_node)
            dept = clean_text(row.get("department"))
            if dept:
                _node(conn, f"dept:{dept}", "Department", dept)
                _edge(conn, scheme_node, "ADMINISTERED_BY", f"dept:{dept}")
            for cat in filter(None, (c.strip() for c in clean_text(row.get("categories")).split(","))):
                _node(conn, f"category:{cat}", "Category", cat)
                _edge(conn, scheme_node, "IN_CATEGORY", f"category:{cat}")
            for ben in filter(None, (b.strip() for b in clean_text(row.get("target_beneficiaries")).split(","))):
                _node(conn, f"beneficiary:{ben}", "BeneficiaryGroup", ben)
                _edge(conn, scheme_node, "TARGETS", f"beneficiary:{ben}")
            for u in urls:
                if u["url"]:
                    _node(conn, f"source:{u['url']}", "Source", u["label"])
                    _edge(conn, scheme_node, "SUPPORTED_BY", f"source:{u['url']}")

    report["distinct_names"] = len(seen_names)
    conn.execute(
        "INSERT INTO source_artifacts(artifact_id, filename, sha256, row_count, imported_at, report_json) VALUES (?,?,?,?,?,?)",
        (artifact_id, path.name, digest, report["rows"], imported_at, dumps(report)),
    )
    conn.commit()
    return {"artifact_id": artifact_id, "skipped": False, **report}


def load_rules(conn: sqlite3.Connection, rules_path: str, bundle_version: str) -> dict:
    with open(rules_path, encoding="utf-8") as f:
        bundle = json.load(f)
    reviewed_at = bundle.get("reviewed_at")
    results = []
    for rule in bundle["rules"]:
        scheme = conn.execute(
            "SELECT scheme_id, name, eligibility_text FROM schemes WHERE scheme_id=?", (rule["scheme_id"],)
        ).fetchone()
        problems = []
        if scheme is None:
            problems.append("scheme_id not found in catalogue")
        else:
            haystack = normalize_for_match(scheme["eligibility_text"])
            for crit in rule["all"] + rule.get("manual_checks", []):
                q = crit.get("quote")
                if q and normalize_for_match(q) not in haystack:
                    problems.append(f"quote for {crit['id']} not found in dataset eligibility text")
        review_status = rule.get("review_status", "team_reviewed")
        if problems:
            review_status = "needs_review"
            rule["review_note"] = "; ".join([rule.get("review_note", "")] + problems).strip("; ")

        prev = conn.execute(
            "SELECT source_verified_at, source_verified_by FROM rules WHERE rule_id=?", (rule["rule_id"],)
        ).fetchone()
        conn.execute(
            """INSERT OR REPLACE INTO rules(rule_id, scheme_id, version, bundle_version, rule_json, review_status,
                reviewed_at, source_verified_at, source_verified_by, active) VALUES (?,?,?,?,?,?,?,?,?,1)""",
            (
                rule["rule_id"], rule["scheme_id"], rule["version"], bundle_version, dumps(rule), review_status,
                reviewed_at, prev["source_verified_at"] if prev else None, prev["source_verified_by"] if prev else None,
            ),
        )
        if scheme is not None:
            conn.execute(
                "UPDATE schemes SET review_status=?, confidence=? WHERE scheme_id=?",
                ("rule_" + review_status, "medium" if review_status == "team_reviewed" else "low", rule["scheme_id"]),
            )
            scheme_node = f"scheme:{rule['scheme_id']}"
            for crit in rule["all"]:
                cnode = f"criterion:{rule['rule_id']}:{crit['id']}"
                _node(conn, cnode, "Criterion", f"{crit['fact']} {crit['op']} {crit.get('value', '')}".strip())
                _edge(conn, scheme_node, "HAS_CRITERION", cnode)
            for doc in rule.get("evidence_requirements", []):
                _node(conn, f"document:{doc}", "Document", doc)
                _edge(conn, scheme_node, "REQUIRES", f"document:{doc}")
            _node(conn, f"rule:{rule['rule_id']}", "RuleVersion", f"{rule['rule_id']} v{rule['version']}")
            _edge(conn, f"rule:{rule['rule_id']}", "EVALUATES", scheme_node)
        results.append({"rule_id": rule["rule_id"], "review_status": review_status, "problems": problems})
    conn.commit()
    return {"bundle_version": bundle_version, "rules": results}


def seed_users(conn: sqlite3.Connection) -> None:
    for username, password, role, display in DEMO_USERS:
        conn.execute(
            "INSERT OR IGNORE INTO users(user_id, username, password_hash, role, display_name) VALUES (?,?,?,?,?)",
            (new_id("USR"), username, generate_password_hash(password), role, display),
        )
    conn.commit()


def bootstrap(conn: sqlite3.Connection, csv_path: str, rules_path: str, bundle_version: str) -> dict:
    init_schema(conn)
    cat = import_catalogue(conn, csv_path)
    rules = load_rules(conn, rules_path, bundle_version)
    seed_users(conn)
    return {"catalogue": cat, "rules": rules}
