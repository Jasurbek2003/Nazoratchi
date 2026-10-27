import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it, vi } from "vitest";
import { CertBadge, FreshnessLabel, GaugeBar } from "./Indicators";
import { ConfirmDialog } from "./Controls";
import { Sparkline, sparkSegments } from "./Sparkline";
import { StatusBadge, StatusDot } from "./Status";
import { STATUS_META, type Status } from "../lib/status";

const ALL: Status[] = ["ok", "warning", "high", "critical", "unknown", "paused", "info"];

describe("holat belgilari: rang + belgi + matn", () => {
  it.each(ALL)("%s: matn, SVG belgi va data-status mavjud", (status) => {
    const { container } = render(<StatusBadge status={status} />);
    expect(screen.getByText(STATUS_META[status].label)).toBeInTheDocument();
    expect(container.querySelector("svg[data-glyph]")).not.toBeNull();
    expect(container.firstElementChild).toHaveAttribute("data-status", status);
  });

  it("har holatning belgi shakli har xil (rangga tayanmaydi)", () => {
    const shapes = ALL.map((status) => {
      const { container, unmount } = render(<StatusBadge status={status} />);
      const d = Array.from(container.querySelectorAll("svg path")).map((p) => p.getAttribute("d")).join("|");
      unmount();
      return d;
    });
    // warning/high uchburchak, ok/critical/paused/info/unknown — o'ziga xos: kamida 6 xil shakl
    expect(new Set(shapes).size).toBeGreaterThanOrEqual(6);
  });

  it("StatusDot ekran o'quvchi uchun 'Holat: ...' etiketiga ega", () => {
    render(<StatusDot status="critical" />);
    expect(screen.getByRole("img", { name: "Holat: kritik" })).toBeInTheDocument();
  });

  it("matnni almashtirsa ham belgi saqlanadi", () => {
    const { container } = render(<StatusBadge status="critical" label="Aloqada emas" />);
    expect(screen.getByText("Aloqada emas")).toBeInTheDocument();
    expect(container.querySelector('svg[data-glyph="critical"]')).not.toBeNull();
  });
});

describe("FreshnessLabel", () => {
  const now = Date.parse("2026-10-27T10:00:00Z");
  it("yangi ma'lumotda 'eskirgan' belgisi yo'q", () => {
    render(<FreshnessLabel iso="2026-10-27T09:59:55Z" now={now} />);
    expect(screen.getByText("5 soniya oldin")).toBeInTheDocument();
    expect(screen.queryByText("eskirgan")).not.toBeInTheDocument();
  });
  it("60 soniyadan eski bo'lsa aniq 'eskirgan'", () => {
    render(<FreshnessLabel iso="2026-10-27T09:55:00Z" now={now} />);
    expect(screen.getByText("5 daqiqa oldin")).toBeInTheDocument();
    expect(screen.getByText("eskirgan")).toBeInTheDocument();
  });
  it("vaqt yo'q bo'lsa 'hech qachon' + eskirgan", () => {
    render(<FreshnessLabel iso={null} now={now} />);
    expect(screen.getByText("hech qachon")).toBeInTheDocument();
    expect(screen.getByText("eskirgan")).toBeInTheDocument();
  });
});

describe("GaugeBar va CertBadge", () => {
  it("eskirgan qiymat chiziq bilan o'chiriladi va etiketda 'eskirgan' deyiladi", () => {
    render(<GaugeBar label="CPU" value={42} stale />);
    expect(screen.getByRole("img")).toHaveAttribute("aria-label", "CPU: 42%, eskirgan");
  });
  it("ma'lumot yo'q bo'lsa tire", () => {
    render(<GaugeBar label="Disk" value={undefined} />);
    expect(screen.getByRole("img")).toHaveAttribute("aria-label", "Disk: ma'lumot yo'q");
  });
  it("sertifikat rangi muddatga qarab (belgi + matn)", () => {
    const { container, rerender } = render(<CertBadge daysLeft={41} />);
    expect(container.firstElementChild).toHaveAttribute("data-status", "ok");
    rerender(<CertBadge daysLeft={5} />);
    expect(container.firstElementChild).toHaveAttribute("data-status", "high");
    expect(screen.getByText("5 kun")).toBeInTheDocument();
    rerender(<CertBadge daysLeft={2} />);
    expect(container.firstElementChild).toHaveAttribute("data-status", "critical");
  });
});

describe("Sparkline", () => {
  it("null nuqtada yo'lni bo'laklarga ajratadi (chiziq tutashmaydi)", () => {
    const segs = sparkSegments([10, 20, null, null, 30, 40], 100, 20);
    expect(segs).toHaveLength(2);
    expect(segs[0]!.match(/M/g)).toHaveLength(1);
    expect(segs[1]!.startsWith("M")).toBe(true);
  });
  it("hammasi null bo'lsa yo'l chizilmaydi va etiket 'ma'lumot yo'q' deydi", () => {
    const { container } = render(<Sparkline values={[null, null]} />);
    expect(container.querySelectorAll("path")).toHaveLength(0);
    expect(screen.getByRole("img")).toHaveAttribute("aria-label", expect.stringContaining("ma'lumot yo'q"));
  });
  it("eskirgan sparkline shtrixli", () => {
    const { container } = render(<Sparkline values={[1, 2, 3]} stale />);
    expect(container.querySelector("path")).toHaveAttribute("stroke-dasharray");
  });
});

describe("ConfirmDialog", () => {
  it("Esc bekor qiladi, tasdiqlash tugmasi onConfirm chaqiradi, oqibat matni ko'rinadi", async () => {
    const onCancel = vi.fn();
    const onConfirm = vi.fn();
    render(
      <ConfirmDialog open title="Pauza" confirmLabel="Pauzaga qo'yish" onCancel={onCancel} onConfirm={onConfirm}>
        <p>Alertlar bostiriladi.</p>
      </ConfirmDialog>,
    );
    expect(screen.getByRole("dialog", { name: "Pauza" })).toBeInTheDocument();
    expect(screen.getByText("Alertlar bostiriladi.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Pauzaga qo'yish" }));
    expect(onConfirm).toHaveBeenCalled();
    await userEvent.keyboard("{Escape}");
    expect(onCancel).toHaveBeenCalled();
  });
  it("fokus dialog ichida qoladi (Tab aylanadi)", async () => {
    render(
      <ConfirmDialog open title="T" confirmLabel="Ha" onCancel={() => {}} onConfirm={() => {}}>
        <p>x</p>
      </ConfirmDialog>,
    );
    await waitFor(() => expect(screen.getByRole("button", { name: "Bekor qilish" })).toHaveFocus());
    await userEvent.tab();
    expect(screen.getByRole("button", { name: "Ha" })).toHaveFocus();
    await userEvent.tab();
    expect(screen.getByRole("button", { name: "Bekor qilish" })).toHaveFocus();
  });
});

// ---- Kontrast (WCAG AA, TZ 13.4.3 / NFR-USA-003): tokens.css dan o'qiladi
function lum(hex: string): number {
  const n = parseInt(hex.slice(1), 16);
  const ch = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((v) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * ch[0]! + 0.7152 * ch[1]! + 0.0722 * ch[2]!;
}
function ratio(a: string, b: string): number {
  const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p);
  return (x! + 0.05) / (y! + 0.05);
}
function tokens(): Record<"light" | "dark", Record<string, string>> {
  const css = readFileSync(resolve(__dirname, "../styles/tokens.css"), "utf8");
  const out = { light: {} as Record<string, string>, dark: {} as Record<string, string> };
  for (const m of css.matchAll(/--([a-z0-9-]+):\s*light-dark\(\s*(#[0-9a-f]{6})\s*,\s*(#[0-9a-f]{6})\s*\)/gi)) {
    out.light[m[1]!] = m[2]!;
    out.dark[m[1]!] = m[3]!;
  }
  return out;
}

describe("kontrast (WCAG AA) ikkala mavzuda", () => {
  const t = tokens();
  const statuses = ["ok", "warning", "high", "critical", "unknown", "info"] as const;

  it("tokenlar o'qildi", () => {
    expect(Object.keys(t.light).length).toBeGreaterThan(20);
    expect(Object.keys(t.dark)).toEqual(Object.keys(t.light));
  });

  for (const mode of ["light", "dark"] as const) {
    const v = t[mode];
    it(`${mode}: asosiy va ikkilamchi matn >= 4.5 (fon, sirt)`, () => {
      for (const bg of ["bg", "surface", "surface-2"]) {
        expect(ratio(v["text"]!, v[bg]!)).toBeGreaterThanOrEqual(4.5);
        expect(ratio(v["muted"]!, v[bg]!)).toBeGreaterThanOrEqual(4.5);
      }
    });
    it.each(statuses)(`${mode}: %s matni o'z foni va sirtda >= 4.5`, (s) => {
      expect(ratio(v[`${s}-fg`]!, v[`${s}-bg`]!)).toBeGreaterThanOrEqual(4.5);
      expect(ratio(v[`${s}-fg`]!, v["surface"]!)).toBeGreaterThanOrEqual(4.5);
    });
    it.each(statuses)(`${mode}: %s belgi/chiziq rangi sirtda >= 3 (grafik/UI elementi)`, (s) => {
      expect(ratio(v[s]!, v["surface"]!)).toBeGreaterThanOrEqual(3);
    });
    it(`${mode}: tugma matni va fokus halqasi`, () => {
      expect(ratio(v["accent-fg"]!, v["accent"]!)).toBeGreaterThanOrEqual(4.5);
      expect(ratio(v["focus"]!, v["surface"]!)).toBeGreaterThanOrEqual(3);
    });
    it(`${mode}: grafik seriyalari sirtda >= 3`, () => {
      expect(ratio(v["series-1"]!, v["surface"]!)).toBeGreaterThanOrEqual(3);
      expect(ratio(v["series-2"]!, v["surface"]!)).toBeGreaterThanOrEqual(3);
    });
  }
});
