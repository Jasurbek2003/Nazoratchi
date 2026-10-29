import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import type { Server } from "../../api/types";
import { apiError, ME, mockFetch, renderPage, server } from "../../test/utils";
import { AgentVersion, agentVersionText, ClockSkew } from "./AgentVersion";

const outdated = (over: Partial<Server> = {}) => server({ agent_version: "nazoratchi-agent/1.0.0", agent_latest: "1.2.0", agent_outdated: true, ...over });

describe("agentVersionText", () => {
  it("sarlavhadagi prefiksni olib tashlaydi", () => {
    expect(agentVersionText("nazoratchi-agent/1.2.3")).toBe("1.2.3");
    expect(agentVersionText("1.2.3")).toBe("1.2.3");
    expect(agentVersionText("")).toBe("—");
  });
});

describe("AgentVersion", () => {
  beforeEach(() => {
    document.cookie = "csrftoken=tok; path=/";
  });

  it("eskirgan agentni belgilaydi va oxirgi versiyani ko'rsatadi", () => {
    renderPage(<AgentVersion server={outdated()} role="viewer" />);
    expect(screen.getByText("1.0.0")).toBeInTheDocument();
    expect(screen.getByText("Yangilash kerak")).toBeInTheDocument();
    expect(screen.getByText("oxirgisi: 1.2.0")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Yangilash" })).not.toBeInTheDocument(); // viewer yangilay olmaydi
  });

  it("yangi yoki noma'lum agentda belgi chiqarmaydi", () => {
    for (const flag of [false, null] as const) {
      const { unmount } = renderPage(<AgentVersion server={server({ agent_outdated: flag, agent_latest: "1.2.0" })} role="owner" />);
      expect(screen.queryByText("Yangilash kerak")).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Yangilash" })).not.toBeInTheDocument();
      unmount();
    }
  });

  it("operator uchun yangilash tugmasi yo'q (faqat owner)", () => {
    renderPage(<AgentVersion server={outdated()} role="operator" />, { me: { ...ME, role: "operator" } });
    expect(screen.getByText("Yangilash kerak")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Yangilash" })).not.toBeInTheDocument();
  });

  it("owner tasdiqlagach POST yuboradi", async () => {
    const mock = mockFetch({ "POST /api/v1/servers/s1/agent-update": { status: 202, body: outdated({ agent_update_to: "1.2.0" }) } });
    renderPage(<AgentVersion server={outdated()} role="owner" />);
    await userEvent.click(screen.getByRole("button", { name: "Yangilash" }));
    expect(screen.getByText(/imzosini tekshiradi/)).toBeInTheDocument();
    await userEvent.click(screen.getAllByRole("button", { name: "Yangilash" }).at(-1)!);
    await vi.waitFor(() => expect(mock.calls.some((c) => c.init.method === "POST" && c.url.pathname === "/api/v1/servers/s1/agent-update")).toBe(true));
  });

  it("backend rad etsa sababini dialogda ko'rsatadi", async () => {
    mockFetch({ "POST /api/v1/servers/s1/agent-update": apiError(409, "conflict", "Core'da agent reliz fayllari (VERSION, SHA256SUMS) yo'q.") });
    renderPage(<AgentVersion server={outdated()} role="owner" />);
    await userEvent.click(screen.getByRole("button", { name: "Yangilash" }));
    await userEvent.click(screen.getAllByRole("button", { name: "Yangilash" }).at(-1)!);
    expect(await screen.findByText(/reliz fayllari/)).toBeInTheDocument();
  });

  it("yangilanish so'ralgan bo'lsa jarayonni ko'rsatadi va bekor qilishga imkon beradi", async () => {
    const mock = mockFetch({ "DELETE /api/v1/servers/s1/agent-update": { body: outdated() } });
    renderPage(<AgentVersion server={outdated({ agent_update_to: "1.2.0" })} role="owner" />);
    expect(screen.getByText("Yangilanmoqda → 1.2.0")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Yangilash" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Bekor qilish" }));
    await vi.waitFor(() => expect(mock.calls.some((c) => c.init.method === "DELETE")).toBe(true));
  });
});

describe("ClockSkew", () => {
  it("o'lchov bo'lmasa chiziqcha", () => {
    renderPage(<ClockSkew seconds={null} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("me'yordagi farqni oddiy ko'rsatadi", () => {
    renderPage(<ClockSkew seconds={0.4} />);
    expect(screen.getByText(/0,4|0\.4/)).toBeInTheDocument();
    expect(screen.getByText("me'yorda")).toBeInTheDocument();
    expect(screen.queryByText("Soat siljigan")).not.toBeInTheDocument();
  });

  it("5 s dan katta farqda (musbat ham, manfiy ham) ogohlantiradi", () => {
    for (const s of [10, -12]) {
      const { unmount } = renderPage(<ClockSkew seconds={s} />);
      expect(screen.getByText("Soat siljigan")).toBeInTheDocument();
      expect(screen.getByText(/chrony/)).toBeInTheDocument();
      unmount();
    }
  });

  it("aynan chegarada (5 s) ogohlantirmaydi", () => {
    renderPage(<ClockSkew seconds={5} />);
    expect(screen.queryByText("Soat siljigan")).not.toBeInTheDocument();
  });
});
