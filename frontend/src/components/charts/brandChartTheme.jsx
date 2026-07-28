/* eslint-disable react-refresh/only-export-components */
import React from "react";

export const BRAND_COLORS = {
  primary: "#4a3d9e",
  deep: "#292173",
  soft: "#c29b3c",
  lavender: "#d9bc72",
  mist: "#ebe6d8",
  midnight: "#171447",
  navy: "#0b0a26",
  success: "#22b07d",
  danger: "#d25f86",
  warning: "#f59e0b",
};

export const BRAND_SERIES_COLORS = [
  "#4a3d9e",
  "#c29b3c",
  "#292173",
  "#d9bc72",
  "#171447",
  "#ebe6d8",
  "#22b07d",
  "#d25f86",
  "#f59e0b",
];

export const BRAND_CHART_TONES = {
  primary: ["#c29b3c", "#292173"],
  secondary: ["#d9bc72", "#4a3d9e"],
  deep: ["#4a3d9e", "#171447"],
  soft: ["#ebe6d8", "#c29b3c"],
  success: ["#22b07d", "#0f7a55"],
  danger: ["#d25f86", "#a83060"],
  warning: ["#f59e0b", "#b45309"],
};

export const BRAND_CHART_AXIS = "#6f6a88";
export const BRAND_CHART_GRID = "rgba(11, 10, 38, 0.12)";
export const BRAND_CHART_CURSOR = "rgba(74, 61, 158, 0.14)";

export const BrandChartGradient = ({ id, variant = "primary", direction = "vertical" }) => {
  const [from, to] = BRAND_CHART_TONES[variant] ?? BRAND_CHART_TONES.primary;
  const axis =
    direction === "horizontal"
      ? { x1: "0", y1: "0", x2: "1", y2: "0" }
      : { x1: "0", y1: "0", x2: "0", y2: "1" };

  return (
    <linearGradient id={id} {...axis}>
      <stop offset="0%" stopColor={from} stopOpacity={1} />
      <stop offset="100%" stopColor={to} stopOpacity={1} />
    </linearGradient>
  );
};

export const BrandAreaGradient = ({ id, variant = "primary" }) => {
  const [from] = BRAND_CHART_TONES[variant] ?? BRAND_CHART_TONES.primary;
  return (
    <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
      <stop offset="5%" stopColor={from} stopOpacity={0.28} />
      <stop offset="95%" stopColor={from} stopOpacity={0.03} />
    </linearGradient>
  );
};

export const brandDonutSegments = (pct, total = 100) => {
  const rest = total - pct;
  return `conic-gradient(${BRAND_COLORS.primary} 0 ${pct}%, ${BRAND_COLORS.lavender} ${pct}% ${pct + rest * 0.48}%, ${BRAND_COLORS.mist} ${pct + rest * 0.48}% 100%)`;
};

/** Tailwind-friendly stat icon tint classes keyed by brand color name */
export const STAT_ICON_TINTS = {
  primary: { bg: "bg-[#4a3d9e]/15", text: "text-[#4a3d9e]" },
  soft: { bg: "bg-[#c29b3c]/15", text: "text-[#a37f2c]" },
  deep: { bg: "bg-[#292173]/15", text: "text-[#292173]" },
  danger: { bg: "bg-[#d25f86]/15", text: "text-[#d25f86]" },
  warning: { bg: "bg-[#f59e0b]/15", text: "text-[#f59e0b]" },
  success: { bg: "bg-[#22b07d]/15", text: "text-[#22b07d]" },
};

export function statIconClasses(key) {
  const tint = STAT_ICON_TINTS[key] ?? STAT_ICON_TINTS.primary;
  return `${tint.bg} ${tint.text}`;
}
