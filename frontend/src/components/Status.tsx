import { memo } from "react";
import { STATUS_META, type Status } from "../lib/status";

/** Holat = rang + belgi + matn (TZ 13.4.1): rang yagona signal emas. */
export const STATUS_CLASS: Record<Status, { chip: string; text: string; bar: string; solid: string }> = {
  ok: { chip: "bg-ok-bg text-ok-fg border-ok/50", text: "text-ok-fg", bar: "bg-ok", solid: "text-ok" },
  warning: { chip: "bg-warning-bg text-warning-fg border-warning/60", text: "text-warning-fg", bar: "bg-warning", solid: "text-warning" },
  high: { chip: "bg-high-bg text-high-fg border-high/60", text: "text-high-fg", bar: "bg-high", solid: "text-high" },
  critical: { chip: "bg-critical-bg text-critical-fg border-critical/60", text: "text-critical-fg", bar: "bg-critical", solid: "text-critical" },
  unknown: { chip: "bg-unknown-bg text-unknown-fg border-unknown/50", text: "text-unknown-fg", bar: "bg-unknown", solid: "text-unknown" },
  paused: { chip: "bg-unknown-bg text-unknown-fg border-unknown border-dashed", text: "text-unknown-fg", bar: "bg-unknown", solid: "text-unknown" },
  info: { chip: "bg-info-bg text-info-fg border-info/50", text: "text-info-fg", bar: "bg-info", solid: "text-info" },
};

export function StatusIcon({ status, size = 14 }: { status: Status; size?: number }) {
  const common = {
    width: size,
    height: size,
    viewBox: "0 0 16 16",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 2,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
    focusable: false,
    "data-glyph": status,
  };
  switch (status) {
    case "ok":
      return (
        <svg {...common}>
          <path d="M3 8.5l3.2 3.2L13 4.8" />
        </svg>
      );
    case "warning":
      return (
        <svg {...common}>
          <path d="M8 2.5L14.2 13H1.8L8 2.5z" />
        </svg>
      );
    case "high":
      return (
        <svg {...common}>
          <path d="M8 1.8L14.4 11.5H1.6L8 1.8z" />
          <path d="M3.6 14.4h8.8" />
        </svg>
      );
    case "critical":
      return (
        <svg {...common}>
          <path d="M4 4l8 8M12 4l-8 8" />
        </svg>
      );
    case "paused":
      return (
        <svg {...common}>
          <path d="M5.5 3.5v9M10.5 3.5v9" />
        </svg>
      );
    case "info":
      return (
        <svg {...common}>
          <path d="M8 7v5M8 4.2v.1" />
        </svg>
      );
    default:
      return (
        <svg {...common}>
          <path d="M5.8 6.2a2.3 2.3 0 114 1.5c-.8.7-1.8 1-1.8 2.3M8 12.4v.1" />
        </svg>
      );
  }
}

export interface StatusBadgeProps {
  status: Status;
  /** Standart matn o'rniga (masalan, "Onlayn"). Belgi va rang saqlanadi. */
  label?: string;
  size?: "sm" | "md";
}

export const StatusBadge = memo(function StatusBadge({ status, label, size = "md" }: StatusBadgeProps) {
  const text = label ?? STATUS_META[status].label;
  return (
    <span
      data-status={status}
      className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full border font-medium leading-none ${STATUS_CLASS[status].chip} ${
        size === "sm" ? "px-1.5 py-[3px] text-xs" : "px-2 py-1 text-[13px]"
      }`}
    >
      <StatusIcon status={status} size={size === "sm" ? 12 : 14} />
      <span>{text}</span>
    </span>
  );
});

/** Kichik nuqta: rang + `aria-label`; shakl ham holatga qarab o'zgaradi (belgi). */
export const StatusDot = memo(function StatusDot({ status, label }: { status: Status; label?: string }) {
  const aria = `Holat: ${(label ?? STATUS_META[status].label).toLowerCase()}`;
  return (
    <span
      role="img"
      aria-label={aria}
      data-status={status}
      className={`inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full ${STATUS_CLASS[status].chip} border`}
    >
      <StatusIcon status={status} size={11} />
    </span>
  );
});
