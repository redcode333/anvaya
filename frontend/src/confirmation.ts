import type { Fact } from "./api";

/** Pending facts split into those confirm-all may cover and those that need their own read-back confirmation. */
export function splitPending(facts: Fact[]): { individual: Fact[]; bulk: Fact[] } {
  const pending = facts.filter((f) => !f.confirmed);
  const one = (f: Fact) => f.confirm_individually ?? f.high_impact;
  return { individual: pending.filter(one), bulk: pending.filter((f) => !one(f)) };
}
