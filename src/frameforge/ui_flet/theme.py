"""Locked v0.5 light SaaS design tokens (Flet)."""

from __future__ import annotations

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
