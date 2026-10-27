import type { ReactNode } from "react";

// Building blocks the staff pages share, so each page reads as: a row of at-a-glance numbers, then tabs, then one panel.

export type TabDef<T extends string> = { id: T; label: string; count?: number | string };

/** Section tabs. Only the chosen panel is shown, so a long page becomes several short ones. */
export function Tabs<T extends string>({ tabs, value, onChange, label }: {
  tabs: TabDef<T>[]; value: T; onChange: (id: T) => void; label: string;
}) {
  return (
    <div className="tabs" role="tablist" aria-label={label}>
      {tabs.map((t) => (
        <button key={t.id} type="button" role="tab" aria-selected={value === t.id} className={value === t.id ? "active" : ""} onClick={() => onChange(t.id)}>
          {t.label}{t.count !== undefined && <span className="tab-count">{t.count}</span>}
        </button>
      ))}
    </div>
  );
}

/** One number with its label. `tone` colours the number when it needs attention (warn) or is a problem (bad). */
export function Stat({ label, value, tone, hint }: { label: string; value: ReactNode; tone?: "ok" | "warn" | "bad"; hint?: string }) {
  return (
    <div className={`stat${tone ? ` ${tone}` : ""}`}>
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
      {hint && <div className="stat-hint">{hint}</div>}
    </div>
  );
}

export const Stats = ({ children }: { children: ReactNode }) => <div className="stats">{children}</div>;

/** Page title with a one-line description under it and any page actions on the right. */
export function PageHead({ title, sub, children }: { title: string; sub?: string; children?: ReactNode }) {
  return (
    <div className="page-head">
      <div><h1>{title}</h1>{sub && <p className="muted small">{sub}</p>}</div>
      {children && <div className="row">{children}</div>}
    </div>
  );
}
