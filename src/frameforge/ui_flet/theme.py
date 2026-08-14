"""Locked v0.5 light SaaS design tokens (Flet)."""

from __future__ import annotations

from typing import Any

# Hex tokens from the v0.5 mockups. Light theme only.
COLORS: dict[str, str] = {
    "app_bg": "#F8FAFC",
    "surface": "#FFFFFF",
    "border": "#E2E8F0",
    "text_primary": "#0F172A",
    "text_secondary": "#64748B",
    "accent": "#2563EB",
    "select": "#EFF6FF",
    "progress": "#3B82F6",
    "success": "#10B981",
    "success_bg": "#ECFDF5",
    "danger": "#EF4444",
    "danger_bg": "#FEF2F2",
    "warn": "#F59E0B",
    "warn_bg": "#FFFBEB",
}

RADIUS_CARD = 12
RADIUS_PILL = 999
FONT_FAMILY = "Segoe UI"
WINDOW_WIDTH = 1100
WINDOW_HEIGHT = 720
TAB_LABELS: tuple[str, ...] = ("Queue", "History", "Thumbnails")

# Widget elevation only — never page.window.shadow (that revives the drag ghost).
ELEVATION_REST: dict[str, Any] = {
    "blur_radius": 8,
    "spread_radius": 0,
    "color": "#0F172A14",
    "offset": (0, 1),
}
ELEVATION_HOVER: dict[str, Any] = {
    "blur_radius": 20,
    "spread_radius": 0,
    "color": "#0F172A2E",
    "offset": (0, 6),
}
ELEVATION_PRESS: dict[str, Any] = {
    "blur_radius": 4,
    "spread_radius": 0,
    "color": "#0F172A1A",
    "offset": (0, 1),
}
ELEVATION_SELECTED: dict[str, Any] = {
    "blur_radius": 12,
    "spread_radius": 0,
    "color": "#2563EB22",
    "offset": (0, 2),
}
