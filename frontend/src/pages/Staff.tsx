import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { PageHead } from "../AdminUI";
import { StaffBar, StaffLogin } from "../components";
import { useApp } from "../state";

type Tile = { to: string; title: string; body: string; roles: string[]; group: "work" | "admin" };
const TILES: Tile[] = [
  { to: "/kiosk", title: "Kiosk", body: "Start temporary citizen sessions on this device.", roles: ["operator", "admin"], group: "work" },
  { to: "/reviewer", title: "Reviewer", body: "Open cases waiting for a human decision.", roles: ["reviewer", "admin"], group: "work" },
  { to: "/admin/schemes", title: "Catalogue", body: "Scheme rules, their sources and how fresh they are.", roles: ["reviewer", "admin"], group: "work" },
  { to: "/admin/security", title: "Security", body: "Staff two-step sign-in, background jobs and the auth audit log.", roles: ["admin"], group: "admin" },
  { to: "/test-runs", title: "TC1–TC5", body: "Run and inspect the official test scenarios.", roles: ["admin"], group: "admin" },
];
const GROUPS: { id: Tile["group"]; title: string }[] = [{ id: "work", title: "Daily work" }, { id: "admin", title: "Administration" }];

/** What needs attention, per tile. Each number is optional: a failed call just leaves that tile without a badge. */
type Badge = { text: string; warn: boolean };

function useBadges(role: string | undefined): Record<string, Badge> {
  const [badges, setBadges] = useState<Record<string, Badge>>({});
  useEffect(() => {
    if (!role) return;
    let live = true;
    const put = (to: string, b: Badge | null) => { if (live && b) setBadges((x) => ({ ...x, [to]: b })); };
    const ask = <T,>(path: string) => api<T>(path).catch(() => null);
    if (role === "reviewer" || role === "admin") {
      ask<{ cases: unknown[] }>("/reviewer/cases?status=PENDING_REVIEW").then((r) =>
        put("/reviewer", r && { text: r.cases.length ? `${r.cases.length} waiting` : "queue is empty", warn: r.cases.length > 0 }));
      ask<{ rules: { source_verified_at: string | null }[] }>("/admin/schemes/freshness").then((r) => {
        const n = r ? r.rules.filter((x) => !x.source_verified_at).length : 0;
        put("/admin/schemes", r && { text: n ? `${n} rules to verify` : "all rules verified", warn: n > 0 });
      });
    }
    if (role === "admin") {
      Promise.all([ask<{ staff: { mfa_enrolled: boolean }[] }>("/admin/staff"), ask<{ runs: { status: string }[] }>("/admin/jobs")]).then(([s, j]) => {
        const noMfa = s ? s.staff.filter((x) => !x.mfa_enrolled).length : 0;
        const failed = j ? j.runs.filter((x) => x.status !== "success").length : 0;
        const parts = [noMfa ? `${noMfa} without two-step` : "", failed ? `${failed} failed jobs` : ""].filter(Boolean);
        put("/admin/security", (s || j) && { text: parts.length ? parts.join(" · ") : "all clear", warn: parts.length > 0 });
      });
    }
    return () => { live = false; };
  }, [role]);
  return badges;
}

/** The one door for staff. Signed out: the sign-in form (any staff role). Signed in: only the tools that role may use,
 *  grouped, each with what needs attention. Signing out stays on this page, so signing back in (as the same or another
 *  role) is always one step away. */
export default function Staff() {
  const { staff } = useApp();
  const badges = useBadges(staff?.role);
  if (!staff) return <StaffLogin roles={["operator", "reviewer", "admin"]} title="Staff sign-in"
    hint="For operators, reviewers and administrators. Citizens do not need an account: use Citizen." />;
  const tiles = TILES.filter((x) => x.roles.includes(staff.role));
  return (
    <div className="stack">
      <StaffBar />
      <PageHead title="Staff area" sub={`Signed in as ${staff.role}. Your tools are below; numbers show what needs attention.`} />
      {GROUPS.map((g) => {
        const inGroup = tiles.filter((x) => x.group === g.id);
        if (!inGroup.length) return null;
        return (
          <section key={g.id} className="stack">
            <h2 className="group-title">{g.title}</h2>
            <div className="grid two">
              {inGroup.map((x) => (
                <Link key={x.to} to={x.to} className="card staff-tile">
                  <h2>{x.title}</h2><p className="muted small">{x.body}</p>
                  {badges[x.to] && <span className={`chip ${badges[x.to].warn ? "off" : "on"}`}>{badges[x.to].text}</span>}
                </Link>
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}
