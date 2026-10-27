import { describe, expect, it } from "vitest";
import {
  formatAgo,
  formatAxisTime,
  formatBytes,
  formatDateTime,
  formatDaysLeft,
  formatDuration,
  formatNumber,
  formatPercent,
  formatRate,
  safeTimeZone,
} from "./format";
import { freshness, isStale } from "./freshness";
import { certStatus, severityStatus, statusRank, usageStatus, worstStatus } from "./status";
import { flattenFacts } from "./facts";
import { describeEvent } from "./incident";

describe("vaqt formatlash", () => {
  it("UTC vaqtni Asia/Tashkent (UTC+5) da ko'rsatadi", () => {
    expect(formatDateTime("2026-10-22T09:35:00Z", "Asia/Tashkent")).toBe("2026-10-22 14:35");
    expect(formatDateTime("2026-10-22T09:35:00Z")).toBe("2026-10-22 14:35");
  });
  it("boshqa zonani qo'llaydi va noto'g'ri zonada standartga qaytadi", () => {
    expect(formatDateTime("2026-10-22T09:35:00Z", "UTC")).toBe("2026-10-22 09:35");
    expect(safeTimeZone("Yo'q/Zona")).toBe("Asia/Tashkent");
    expect(formatDateTime("2026-10-22T09:35:00Z", "Yo'q/Zona")).toBe("2026-10-22 14:35");
  });
  it("yarim tunda 24:00 emas, 00:00 chiqaradi", () => {
    expect(formatDateTime("2026-10-22T19:05:00Z", "Asia/Tashkent")).toBe("2026-10-23 00:05");
  });
  it("noto'g'ri qiymatda tire qaytaradi", () => {
    expect(formatDateTime("bu sana emas")).toBe("—");
    expect(formatDateTime(null)).toBe("—");
  });
  it("nisbiy vaqt: hozir / soniya / daqiqa / soat / kun", () => {
    expect([2, 3, 59, 60, 125, 3600, 7200, 3 * 86400].map(formatAgo)).toEqual([
      "hozir",
      "hozir",
      "59 soniya oldin",
      "1 daqiqa oldin",
      "2 daqiqa oldin",
      "1 soat oldin",
      "2 soat oldin",
      "3 kun oldin",
    ]);
  });
  it("davomiylik: ikki eng katta birlik", () => {
    expect(formatDuration(4 * 86400 + 3 * 3600 + 20)).toBe("4 kun 3 soat");
    expect(formatDuration(12 * 60)).toBe("12 daqiqa");
    expect(formatDuration(35)).toBe("35 soniya");
    expect(formatDuration(-1)).toBe("—");
  });
  it("grafik o'qi vaqti foydalanuvchi zonasida", () => {
    const t = Date.parse("2026-10-22T09:30:00Z") / 1000;
    expect(formatAxisTime(t, "Asia/Tashkent", false)).toBe("14:30");
    expect(formatAxisTime(t, "Asia/Tashkent", true)).toBe("22 okt");
  });
});

describe("son va hajm formatlash", () => {
  it("o'zbekcha: bo'sh joy minglik, vergul kasr", () => {
    expect(formatNumber(12345.6).replace(/\s/g, " ")).toBe("12 345,6");
  });
  it("foiz yopishiq", () => {
    expect(formatPercent(78.4)).toBe("78%");
    expect(formatPercent(null)).toBe("—");
  });
  it("bayt 1024 asosida", () => {
    expect(formatBytes(0)).toBe("0 bayt");
    expect(formatBytes(1536)).toContain("KB");
    expect(formatBytes(1024 * 1024 * 46)).toBe("46 MB");
    expect(formatRate(2 * 1024 * 1024)).toBe("2 MB/s");
  });
  it("sertifikat qolgan kun matni", () => {
    expect(formatDaysLeft(41)).toBe("41 kun");
    expect(formatDaysLeft(-3)).toBe("3 kun oldin tugagan");
  });
});

describe("eskirgan mantig'i", () => {
  const now = Date.parse("2026-10-27T10:00:00Z");
  it("60 soniyagacha yangi, undan keyin eskirgan", () => {
    expect(isStale("2026-10-27T09:59:30Z", now)).toBe(false);
    expect(isStale("2026-10-27T09:59:00Z", now)).toBe(false);
    expect(isStale("2026-10-27T09:58:59Z", now)).toBe(true);
  });
  it("vaqt yo'q yoki yaroqsiz bo'lsa eskirgan (hech qachon 'hozirgi' emas)", () => {
    expect(isStale(null, now)).toBe(true);
    expect(isStale("xato", now)).toBe(true);
    expect(freshness(null, now)).toBe("never");
    expect(freshness("2026-10-27T09:50:00Z", now)).toBe("stale");
    expect(freshness("2026-10-27T09:59:50Z", now)).toBe("fresh");
  });
  it("maxsus chegara (probe: 3 interval)", () => {
    expect(isStale("2026-10-27T09:58:00Z", now, 210)).toBe(false);
    expect(isStale("2026-10-27T09:55:00Z", now, 210)).toBe(true);
  });
});

describe("holat aggregatsiyasi (TZ 13.4.2)", () => {
  it("eng yomoni: critical > high > warning > unknown > ok", () => {
    expect(worstStatus(["ok", "warning", "critical", "high"])).toBe("critical");
    expect(worstStatus(["ok", "warning", "high"])).toBe("high");
    expect(worstStatus(["ok", "unknown", "warning"])).toBe("warning");
  });
  it("unknown faqat qolganlar ok bo'lsa ko'rinadi", () => {
    expect(worstStatus(["ok", "unknown", "ok"])).toBe("unknown");
    expect(worstStatus(["unknown", "critical"])).toBe("critical");
  });
  it("bo'sh ro'yxat -> unknown; pauza ok dan yomon emas", () => {
    expect(worstStatus([])).toBe("unknown");
    expect(statusRank("paused")).toBe(statusRank("ok"));
  });
  it("ahamiyat -> holat, noma'lum ahamiyat -> unknown", () => {
    expect(severityStatus("high")).toBe("high");
    expect(severityStatus("xyz")).toBe("unknown");
  });
  it("sertifikat chegaralari 21/7/3", () => {
    expect([certStatus(41), certStatus(21), certStatus(20), certStatus(7), certStatus(6), certStatus(3), certStatus(-1), certStatus(null)]).toEqual([
      "ok",
      "warning",
      "warning",
      "high",
      "high",
      "critical",
      "critical",
      "unknown",
    ]);
  });
  it("foiz chegaralari", () => {
    expect([usageStatus(50), usageStatus(85), usageStatus(95), usageStatus(null)]).toEqual(["ok", "warning", "critical", "unknown"]);
  });
});

describe("facts va incident voqealari", () => {
  it("facts tekis ro'yxatga aylanadi, bayt o'lchamlari formatlanadi", () => {
    const rows = flattenFacts({ os: "Ubuntu 24.04", mem_total_bytes: 8 * 1024 ** 3, cpu_count: 4, nested: { a: 1 }, ports: [22, 80] });
    const byKey = Object.fromEntries(rows.map((r) => [r.key, r.value]));
    expect(byKey["os"]).toBe("Ubuntu 24.04");
    expect(byKey["mem_total_bytes"]).toBe("8 GB");
    expect(byKey["nested.a"]).toBe("1");
    expect(byKey["ports"]).toBe("22, 80");
  });
  it("voqealar o'zbekcha tavsiflanadi", () => {
    expect(describeEvent({ type: "acked", user: "jasur", data: { comment: "ko'rdim" } })).toBe("jasur qabul qildi: «ko'rdim»");
    expect(describeEvent({ type: "severity_changed", user: null, data: { old: "warning", new: "critical" } })).toContain("diqqat → kritik");
    expect(describeEvent({ type: "resolved", user: null, data: {} })).toBe("Avtomatik yopildi");
    expect(describeEvent({ type: "boshqa", user: null, data: {} })).toBe("boshqa");
  });
});
