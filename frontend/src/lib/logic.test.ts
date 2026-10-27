import { describe, expect, it } from "vitest";
import type { LatestResponse, Probe, Project } from "../api/types";
import { incident, server } from "../test/utils";
import { collectTags, filterProjects, filterServers } from "./filters";
import { nullRuns, sparkValues, sumSeries, tableRows, toAligned } from "./chart";
import { projectHealth, probeStale } from "./projectStatus";
import { extractVitals, serverDisplayStatus } from "./serverStatus";
import { buildSummary } from "./summary";

const NOW = Date.parse("2026-10-27T10:00:00Z");
const iso = (secondsAgo: number) => new Date(NOW - secondsAgo * 1000).toISOString();

describe("Dashboard xulosasi", () => {
  const fresh = (over = {}) => server({ id: "s1", last_seen_at: iso(5), ...over });

  it("incident ham, muammoli server ham yo'q -> 'Hammasi joyida'", () => {
    const s = buildSummary({ incidents: [], servers: [fresh()], now: NOW });
    expect(s.headline).toBe("Hammasi joyida");
    expect(s.level).toBe("ok");
    expect(s.problems).toHaveLength(0);
  });

  it("ochiq incidentlar sonini 'N ta muammo' deb yozadi va eng og'irini darajaga qo'yadi", () => {
    const s = buildSummary({
      incidents: [incident({ id: "a", severity: "warning" }), incident({ id: "b", severity: "critical", title: "Server o'chdi" })],
      servers: [fresh()],
      now: NOW,
    });
    expect(s.headline).toBe("2 ta muammo");
    expect(s.level).toBe("critical");
    expect(s.problems.map((p) => p.incident?.id)).toEqual(["b", "a"]);
  });

  it("bir xil ahamiyatda yangisi tepada", () => {
    const old = incident({ id: "old", severity: "high", started_at: iso(7200) });
    const recent = incident({ id: "new", severity: "high", started_at: iso(60) });
    const s = buildSummary({ incidents: [old, recent], servers: [fresh()], now: NOW });
    expect(s.problems.map((p) => p.incident?.id)).toEqual(["new", "old"]);
  });

  it("yopilgan incident hisobga olinmaydi; qabul qilingani hali muammo", () => {
    const s = buildSummary({
      incidents: [incident({ id: "r", status: "resolved" }), incident({ id: "k", status: "acknowledged", severity: "high" })],
      servers: [fresh()],
      now: NOW,
    });
    expect(s.headline).toBe("1 ta muammo");
    expect(s.level).toBe("high");
  });

  it("bostirilgan (silence) incident muammo sonini oshirmaydi, lekin alohida sanaladi", () => {
    const s = buildSummary({ incidents: [incident({ suppressed: true })], servers: [fresh()], now: NOW });
    expect(s.headline).toBe("Hammasi joyida");
    expect(s.suppressed).toBe(1);
  });

  it("incidentsiz ham aloqasi uzilgan server yashirinmaydi", () => {
    const s = buildSummary({ incidents: [], servers: [fresh({ id: "s2", name: "backup-1", status: "offline", last_seen_at: iso(900) })], now: NOW });
    expect(s.headline).toBe("1 ta muammo");
    expect(s.problems[0]).toMatchObject({ kind: "server", status: "critical", serverId: "s2" });
  });

  it("onlayn deb belgilangan, lekin 60 soniyadan beri jim server 'ma'lumot kelmayapti' (hozirgi emas)", () => {
    const s = buildSummary({ incidents: [], servers: [fresh({ last_seen_at: iso(300) })], now: NOW });
    expect(s.level).toBe("unknown");
    expect(s.problems[0]?.title).toContain("Ma'lumot kelmayapti");
    expect(s.headline).not.toBe("Hammasi joyida");
  });

  it("serverning o'z incidenti bor bo'lsa, takroriy 'aloqada emas' qo'shilmaydi", () => {
    const s = buildSummary({
      incidents: [incident({ scope_key: "host:s2", severity: "critical" })],
      servers: [fresh({ id: "s2", status: "offline", last_seen_at: iso(900) })],
      now: NOW,
    });
    expect(s.problems).toHaveLength(1);
  });
});

describe("server holati", () => {
  it("pauza, yangi, aloqasiz holatlari", () => {
    expect(serverDisplayStatus(server({ status: "paused" }), [], NOW).status).toBe("paused");
    expect(serverDisplayStatus(server({ status: "new", last_seen_at: null }), [], NOW)).toMatchObject({ status: "unknown", stale: true });
    expect(serverDisplayStatus(server({ status: "offline", last_seen_at: iso(900) }), [], NOW)).toMatchObject({ status: "critical", stale: true });
  });
  it("onlayn+yangi -> ok; incident bo'lsa eng yomon ahamiyat; eskirgan -> unknown", () => {
    const s = server({ last_seen_at: iso(10) });
    expect(serverDisplayStatus(s, [], NOW).status).toBe("ok");
    expect(serverDisplayStatus(s, [incident({ severity: "warning" }), incident({ id: "x", severity: "high" })], NOW).status).toBe("high");
    expect(serverDisplayStatus(server({ last_seen_at: iso(120) }), [incident()], NOW)).toMatchObject({ status: "unknown", stale: true });
  });
  it("metrikalar: disk — eng to'lgan mount, tarmoq — yig'indi, eskirgan belgisi", () => {
    const latest: LatestResponse = {
      server_id: "s1",
      metrics: {
        cpu_busy_percent: [{ labels: {}, time: iso(5), value: 12 }],
        mem_used_percent: [{ labels: {}, time: iso(300), value: 40 }],
        fs_used_percent: [
          { labels: { mount: "/" }, time: iso(5), value: 78 },
          { labels: { mount: "/data" }, time: iso(5), value: 91 },
        ],
        net_rx_bytes_per_sec: [
          { labels: { iface: "eth0" }, time: iso(5), value: 100 },
          { labels: { iface: "eth1" }, time: iso(5), value: 50 },
        ],
      },
    };
    const v = extractVitals(latest, NOW);
    expect(v.cpu).toMatchObject({ value: 12, stale: false });
    expect(v.mem).toMatchObject({ value: 40, stale: true });
    expect(v.disk).toMatchObject({ value: 91, detail: "/data" });
    expect(v.rx?.value).toBe(150);
    expect(v.tx).toBeUndefined();
  });
});

describe("grafik ma'lumoti: null = bo'shliq", () => {
  it("null nuqtalarni saqlaydi (tutashtirmaydi) va vaqtni soniyaga o'tkazadi", () => {
    const { xs, ys } = toAligned([
      [
        [1000, 10],
        [2000, null],
        [3000, 30],
      ],
    ]);
    expect(xs).toEqual([1, 2, 3]);
    expect(ys[0]).toEqual([10, null, 30]);
  });
  it("turli vaqtli seriyalarni birlashtiradi, yo'q joyga null qo'yadi", () => {
    const { xs, ys } = toAligned([
      [[1000, 1], [3000, 3]],
      [[2000, 20], [3000, 30]],
    ]);
    expect(xs).toEqual([1, 2, 3]);
    expect(ys[0]).toEqual([1, null, 3]);
    expect(ys[1]).toEqual([null, 20, 30]);
  });
  it("NaN/Infinity ham null bo'ladi", () => {
    expect(toAligned([[[1000, Number.NaN], [2000, Infinity]]]).ys[0]).toEqual([null, null]);
  });
  it("sumSeries: yig'indi; hammasi null bo'lsa null (0 emas)", () => {
    const sum = sumSeries([
      [[1000, 1], [2000, null], [3000, null]],
      [[1000, 2], [2000, 5], [3000, null]],
    ]);
    expect(sum).toEqual([[1000, 3], [2000, 5], [3000, null]]);
  });
  it("nullRuns: bo'shliq oralig'ini qo'shni haqiqiy nuqtalargacha kengaytiradi", () => {
    const xs = [1, 2, 3, 4, 5, 6];
    const ys = [[1, null, null, 4, null, 6]];
    expect(nullRuns(xs, ys)).toEqual([[1, 4], [4, 6]]);
    expect(nullRuns(xs, [[1, 2, 3, 4, 5, 6]])).toEqual([]);
  });
  it("faqat bitta seriya bo'sh bo'lsa, boshqasi bor joy bo'shliq emas", () => {
    expect(nullRuns([1, 2, 3], [[1, null, 3], [1, 2, 3]])).toEqual([]);
  });
  it("tableRows va sparkValues chegaralari", () => {
    const xs = Array.from({ length: 100 }, (_, i) => i);
    expect(tableRows(xs, [xs.map((x) => x)], 10).length).toBeLessThanOrEqual(10);
    expect(sparkValues(Array.from({ length: 100 }, (_, i) => [i, i] as [number, number]), 60)).toHaveLength(60);
    expect(sparkValues(undefined)).toEqual([]);
  });
});

describe("filtr va qidiruv", () => {
  const servers = [
    server({ id: "1", name: "main-2", tags: ["prod", "contabo"], status: "online", public_ipv4: "164.68.105.194" }),
    server({ id: "2", name: "backup-1", tags: ["backup"], status: "offline", public_ipv4: "10.0.0.7", provider: "Hetzner" }),
    server({ id: "3", name: "core-1", tags: ["prod"], status: "paused", public_ipv4: null }),
  ];
  it("holat bo'yicha", () => {
    expect(filterServers(servers, { status: "offline" }).map((s) => s.id)).toEqual(["2"]);
  });
  it("teg bo'yicha", () => {
    expect(filterServers(servers, { tag: "prod" }).map((s) => s.id)).toEqual(["1", "3"]);
  });
  it("qidiruv: nom, IP boshi, provayder, teg; katta-kichik harf farqsiz", () => {
    expect(filterServers(servers, { q: "MAIN" }).map((s) => s.id)).toEqual(["1"]);
    expect(filterServers(servers, { q: "164.68" }).map((s) => s.id)).toEqual(["1"]);
    expect(filterServers(servers, { q: "hetzner" }).map((s) => s.id)).toEqual(["2"]);
    expect(filterServers(servers, { q: "backup" }).map((s) => s.id)).toEqual(["2"]);
  });
  it("filtrlar birgalikda (VA) ishlaydi; natijasiz bo'lsa bo'sh", () => {
    expect(filterServers(servers, { tag: "prod", status: "paused" }).map((s) => s.id)).toEqual(["3"]);
    expect(filterServers(servers, { tag: "prod", q: "backup" })).toEqual([]);
  });
  it("teglar noyob va tartiblangan", () => {
    expect(collectTags(servers)).toEqual(["backup", "contabo", "prod"]);
  });

  const projects = [
    { id: "p1", slug: "nazar", name: "Nazar", kind: "compose", owner_name: "", tags: [], domains_info: [{ id: "d1", fqdn: "nazar.avlo.ai", status: "active" }], servers_info: [{ server_id: "1", server: "main-2", environment: "production", ports: [8001] }] },
    { id: "p2", slug: "wmg", name: "WMG", kind: "static", owner_name: "Ali", tags: ["mijoz"], domains_info: [], servers_info: [] },
  ] as unknown as Project[];
  it("loyiha qidiruvi: slug, nom, domen, server, egasi, teg", () => {
    expect(filterProjects(projects, { q: "avlo" }).map((p) => p.id)).toEqual(["p1"]);
    expect(filterProjects(projects, { q: "main-2" }).map((p) => p.id)).toEqual(["p1"]);
    expect(filterProjects(projects, { q: "ali" }).map((p) => p.id)).toEqual(["p2"]);
    expect(filterProjects(projects, { q: "mijoz" }).map((p) => p.id)).toEqual(["p2"]);
    expect(filterProjects(projects, { kind: "static" }).map((p) => p.id)).toEqual(["p2"]);
  });
});

describe("loyiha holati (probe'lar)", () => {
  const project = { id: "p1", status: "active" } as Project;
  const probe = (over: Partial<Probe>): Probe =>
    ({ id: "x", project: "p1", enabled: true, state: "up", interval_s: 60, last_run_at: iso(20), type: "http", name: "n", ...over }) as Probe;

  it("hamma tekshiruv ishlasa ok, bittasi yiqilsa critical", () => {
    expect(projectHealth(project, [probe({}), probe({})], NOW).status).toBe("ok");
    const h = projectHealth(project, [probe({}), probe({ state: "down" })], NOW);
    expect(h.status).toBe("critical");
    expect(h.failing).toBe(1);
  });
  it("tekshiruv yo'q -> noma'lum (ok emas)", () => {
    expect(projectHealth(project, [], NOW)).toMatchObject({ status: "unknown", label: "Tekshiruv yo'q" });
  });
  it("eskirgan probe 'up' bo'lsa ham noma'lum", () => {
    expect(probeStale(probe({ last_run_at: iso(1000) }), NOW)).toBe(true);
    expect(projectHealth(project, [probe({ last_run_at: iso(1000) })], NOW).status).toBe("unknown");
  });
  it("arxiv loyiha pauza belgisi bilan; boshqa loyiha probe'lari aralashmaydi", () => {
    expect(projectHealth({ ...project, status: "archived" } as Project, [], NOW).label).toBe("Arxiv");
    expect(projectHealth(project, [probe({ project: "other", state: "down" })], NOW).status).toBe("unknown");
  });
});
