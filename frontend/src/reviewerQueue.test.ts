import { describe, expect, it } from "vitest";
import { ageHours, queueOrder, timeAgo } from "./reviewerQueue";

const NOW = Date.parse("2026-10-27T12:00:00Z");

describe("review queue helpers", () => {
  it("says how long ago, in the unit that reads best", () => {
    expect(timeAgo("2026-10-27T11:59:50Z", NOW)).toBe("just now");
    expect(timeAgo("2026-10-27T11:48:00Z", NOW)).toBe("12 min");
    expect(timeAgo("2026-10-27T09:00:00Z", NOW)).toBe("3 h");
    expect(timeAgo("2026-10-24T12:00:00Z", NOW)).toBe("3 d");
    expect(timeAgo(null, NOW)).toBe("—");
    expect(timeAgo("not a date", NOW)).toBe("—");
  });

  it("never reports a negative age", () => {
    expect(ageHours("2026-10-27T13:00:00Z", NOW)).toBe(0);
    expect(ageHours(undefined, NOW)).toBe(0);
  });

  it("puts the longest-waiting case first, then the rest newest first", () => {
    const rows = [
      { id: "a", status: "REVIEWED", updated_at: "2026-10-27T10:00:00Z" },
      { id: "b", status: "PENDING_REVIEW", updated_at: "2026-10-27T09:00:00Z" },
      { id: "c", status: "PENDING_REVIEW", updated_at: "2026-10-26T09:00:00Z" },
      { id: "d", status: "CORRECTION_REQUESTED", updated_at: "2026-10-27T11:00:00Z" },
    ];
    expect(queueOrder(rows).map((r) => r.id)).toEqual(["c", "b", "d", "a"]);
    expect(rows[0].id).toBe("a");  // the input is not reordered in place
  });
});
