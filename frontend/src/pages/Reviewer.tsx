import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { PageHead, Stat, Stats, Tabs } from "../AdminUI";
import { api } from "../api";
import { ErrorNote, OutcomeBadge, StaffBar, StaffLogin, StatusBadge } from "../components";
import { ageHours, queueOrder, timeAgo } from "../reviewerQueue";
import { useApp } from "../state";

type Filter = "" | "PENDING_REVIEW" | "CORRECTION_REQUESTED" | "REVIEWED";
const LABELS: Record<Filter, string> = { "": "All", PENDING_REVIEW: "Waiting", CORRECTION_REQUESTED: "Correction asked", REVIEWED: "Reviewed" };
const EMPTY: Record<Filter, string> = {
  "": "No cases yet. They appear here when a citizen sends a draft for review.",
  PENDING_REVIEW: "Nothing is waiting. New cases show up here as citizens send them.",
  CORRECTION_REQUESTED: "No case is waiting on a citizen's correction.",
  REVIEWED: "No case has been reviewed yet.",
};

export default function Reviewer() {
  const { staff } = useApp();
  const nav = useNavigate();
  const [filter, setFilter] = useState<Filter>("PENDING_REVIEW");
  const [cases, setCases] = useState<any[] | null>(null);
  const [showTests, setShowTests] = useState(false);
  const [code, setCode] = useState("");
  const [err, setErr] = useState<unknown>(null);

  const isReviewer = staff && ["reviewer", "admin"].includes(staff.role);
  const load = () => api<{ cases: any[] }>("/reviewer/cases").then((r) => setCases(r.cases)).catch(setErr);
  useEffect(() => { if (isReviewer) load(); }, [isReviewer]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!isReviewer) return <StaffLogin roles={["reviewer", "admin"]} title="Reviewer sign-in" hint="Role is checked on the server for every request." />;

  const lookup = async (e: React.FormEvent) => {
    e.preventDefault(); setErr(null);
    try { nav(`/reviewer/case/${(await api<{ case_id: string }>("/reviewer/cases/lookup", { body: { code } })).case_id}`); } catch (x) { setErr(x); }
  };
  const visible = (cases ?? []).filter((c) => showTests || !c.is_test);
  const count = (s: string) => visible.filter((c) => c.status === s).length;
  const waiting = visible.filter((c) => c.status === "PENDING_REVIEW");
  const oldest = waiting.length ? waiting.reduce((a, b) => (Date.parse(a.updated_at) <= Date.parse(b.updated_at) ? a : b)) : null;
  const longest = oldest ? ageHours(oldest.updated_at) : null;
  const shown = queueOrder(filter ? visible.filter((c) => c.status === filter) : visible);

  return (
    <div className="stack">
      <StaffBar><button className="btn small" onClick={load}>Refresh</button></StaffBar>
      <PageHead title="Review queue" sub="Cases citizens sent for a human check. The longest-waiting case is first.">
        <form className="row" onSubmit={lookup}>
          <input type="text" placeholder="Case code ANV-…" value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} aria-label="Case code" style={{ width: 190 }} />
          <button className="btn" type="submit" disabled={!code.trim()}>Open by code</button>
        </form>
      </PageHead>

      <Stats>
        <Stat label="Waiting for review" value={cases ? count("PENDING_REVIEW") : "—"} tone={count("PENDING_REVIEW") ? "warn" : "ok"} />
        <Stat label="Longest wait" value={oldest ? timeAgo(oldest.updated_at) : "—"}
          tone={longest !== null && longest > 24 ? "bad" : longest !== null && longest > 4 ? "warn" : undefined} hint={longest !== null && longest > 24 ? "over a day" : undefined} />
        <Stat label="Correction asked" value={cases ? count("CORRECTION_REQUESTED") : "—"} />
        <Stat label="Reviewed" value={cases ? count("REVIEWED") : "—"} tone="ok" />
      </Stats>

      <div className="row spread">
        <Tabs label="Status filter" value={filter} onChange={setFilter}
          tabs={(Object.keys(LABELS) as Filter[]).map((f) => ({ id: f, label: LABELS[f], count: f ? count(f) : visible.length }))} />
        <label className="row small"><input type="checkbox" checked={showTests} onChange={(e) => setShowTests(e.target.checked)} /> show test-runner cases</label>
      </div>
      <ErrorNote error={err} />

      <div className="case-list">
        {cases === null && !err && <p className="muted">Loading…</p>}
        {cases !== null && shown.length === 0 && (
          <div className="case-empty"><span aria-hidden="true">✓</span><p>{EMPTY[filter]}</p></div>
        )}
        {shown.map((c) => {
          const stale = c.status === "PENDING_REVIEW" && ageHours(c.updated_at) > 24;
          return (
            <Link key={c.case_id} to={`/reviewer/case/${c.case_id}`} className={`case-row s-${c.status}`}>
              <span className="cr-main">
                <b>{c.scheme_name}</b>
                <span className="tiny mono">{c.case_id}</span>
              </span>
              <span className="cr-badges">
                <OutcomeBadge outcome={c.screening_outcome} lang="en" />
                <StatusBadge status={c.status} />
                {c.review_outcome && <span className="chip">{String(c.review_outcome).replace(/_/g, " ")}</span>}
              </span>
              <span className="cr-meta tiny">
                {c.origin}{c.is_test && " · test"}
                <span className={stale ? "cr-stale" : undefined}> · {c.status === "PENDING_REVIEW" ? `waiting ${timeAgo(c.updated_at)}` : `updated ${timeAgo(c.updated_at)} ago`}</span>
              </span>
              <span className="cr-arrow" aria-hidden="true">›</span>
            </Link>
          );
        })}
      </div>
      <p className="tiny">States shown are draft-review states. SUBMITTED_EXTERNAL is reserved for a real, verified government integration and never appears here.</p>
    </div>
  );
}
