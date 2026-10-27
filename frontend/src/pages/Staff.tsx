import { Link } from "react-router-dom";
import { StaffBar, StaffLogin } from "../components";
import { useApp } from "../state";

type Tile = { to: string; title: string; body: string; roles: string[] };
const TILES: Tile[] = [
  { to: "/reviewer", title: "Reviewer", body: "Open cases waiting for a human decision.", roles: ["reviewer", "admin"] },
  { to: "/admin/schemes", title: "Catalogue", body: "Scheme rules, their sources and how fresh they are.", roles: ["reviewer", "admin"] },
  { to: "/admin/security", title: "Security", body: "Staff two-step sign-in and the auth audit log.", roles: ["admin"] },
  { to: "/test-runs", title: "TC1–TC5", body: "Run and inspect the official test scenarios.", roles: ["admin"] },
  { to: "/kiosk", title: "Kiosk", body: "Start temporary citizen sessions on this device.", roles: ["operator", "admin"] },
];

/** The one door for staff. Signed out: the sign-in form (any staff role). Signed in: only the tools that role may use.
 *  Signing out stays on this page, so signing back in (as the same or another role) is always one step away. */
export default function Staff() {
  const { staff } = useApp();
  if (!staff) return <StaffLogin roles={["operator", "reviewer", "admin"]} title="Staff sign-in"
    hint="For operators, reviewers and administrators. Citizens do not need an account: use Citizen." />;
  const tiles = TILES.filter((x) => x.roles.includes(staff.role));
  return (
    <div className="stack">
      <StaffBar />
      <h1>Staff area</h1>
      <div className="grid two">
        {tiles.map((x) => (
          <Link key={x.to} to={x.to} className="card staff-tile">
            <h2>{x.title}</h2><p className="muted small">{x.body}</p>
          </Link>
        ))}
      </div>
    </div>
  );
}
