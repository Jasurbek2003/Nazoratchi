import { describe, expect, it } from "vitest";
import { describeMatcher, maintenanceSchema, silenceEndsAt, silenceSchema, toLocalInput, windowPhase } from "./suppression";
import { backupState, formatHours } from "./backups";

const base = { matchers: [{ label: "server", op: "=" as const, value: "main-2" }], duration: "1h" as const, custom_ends: "", reason: "sabab" };

describe("silenceSchema", () => {
  it("tezkor muddat bilan o'tadi", () => {
    expect(silenceSchema.safeParse(base).success).toBe(true);
  });
  it("bo'sh sabab va qiymatni rad etadi", () => {
    expect(silenceSchema.safeParse({ ...base, reason: "  " }).success).toBe(false);
    expect(silenceSchema.safeParse({ ...base, matchers: [{ label: "server", op: "=", value: "" }] }).success).toBe(false);
  });
  it("maxsus muddat 15 daqiqadan 30 kungacha", () => {
    const at = (ms: number) => toLocalInput(new Date(Date.now() + ms));
    expect(silenceSchema.safeParse({ ...base, duration: "custom", custom_ends: at(5 * 60_000) }).success).toBe(false);
    expect(silenceSchema.safeParse({ ...base, duration: "custom", custom_ends: at(2 * 3600_000) }).success).toBe(true);
    expect(silenceSchema.safeParse({ ...base, duration: "custom", custom_ends: at(40 * 86400_000) }).success).toBe(false);
    expect(silenceSchema.safeParse({ ...base, duration: "custom", custom_ends: "" }).success).toBe(false);
  });
  it("tugash vaqtini hisoblaydi", () => {
    const ends = Date.parse(silenceEndsAt({ ...base, duration: "24h" }));
    expect(Math.abs(ends - Date.now() - 86400_000)).toBeLessThan(5000);
  });
});

describe("maintenanceSchema", () => {
  const ok = { servers: ["s1"], projects: [], starts_at: "2026-10-28T10:00", ends_at: "2026-10-28T12:00", reason: "yangilash" };
  it("to'g'ri qiymat o'tadi", () => expect(maintenanceSchema.safeParse(ok).success).toBe(true));
  it("qamrovsiz, teskari yoki juda uzun oynani rad etadi", () => {
    expect(maintenanceSchema.safeParse({ ...ok, servers: [] }).success).toBe(false);
    expect(maintenanceSchema.safeParse({ ...ok, ends_at: "2026-10-28T09:00" }).success).toBe(false);
    expect(maintenanceSchema.safeParse({ ...ok, ends_at: "2026-12-28T09:00" }).success).toBe(false);
  });
});

describe("yordamchilar", () => {
  it("matcher matni", () => expect(describeMatcher({ label: "project", op: "=~", value: "naz.*" })).toBe("Loyiha =~ naz.*"));
  it("oyna bosqichi", () => {
    const now = Date.now();
    expect(windowPhase({ starts_at: new Date(now + 3600_000).toISOString(), ends_at: "" }, now)).toBe("scheduled");
    expect(windowPhase({ starts_at: new Date(now - 3600_000).toISOString(), ends_at: "" }, now)).toBe("active");
  });
  it("zaxira holati va soat formati", () => {
    expect(backupState("late").status).toBe("warning");
    expect(backupState("nomalum-holat").label).toBe("Noma'lum");
    expect(formatHours(6)).toBe("6 soat");
    expect(formatHours(72)).toBe("3 kun");
    expect(formatHours(null)).toBe("—");
  });
});
