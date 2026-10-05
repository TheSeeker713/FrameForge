"""Upscale onboarding dialog shown before a job starts.

Displays:
  - Model status (smoke identity vs Real-ESRGAN vs missing)
  - Resolution and duration of the source
  - Estimated completion time (probe → fallback)
  - Resource snapshot (CPU / RAM)
  - Hard gate warning when estimate > 4 hours
  - Choices: Proceed | Split into 15-min segments | Cancel

The caller is responsible for:
  1. Gathering the VideoMetrics and UpscaleEstimate (possibly on a background
     thread, since probe() runs ONNX).
  2. Invoking ``upscale_onboarding_dialog`` on the Flet UI thread.
  3. Acting on the chosen action (PROCEED / SPLIT / CANCEL).
"""

from __future__ import annotations

from typing import Any

import flet as ft

from frameforge.ui_flet.theme import COLORS
from frameforge.upscale.onboarding import OnboardingContext  # re-export

# Action constants returned by the dialog callbacks.
ACTION_PROCEED = "proceed"
ACTION_SPLIT = "split"
ACTION_CANCEL = "cancel"

__all__ = [
    "OnboardingContext",
    "ACTION_PROCEED",
    "ACTION_SPLIT",
    "ACTION_CANCEL",
    "upscale_onboarding_dialog",
    "build_onboarding_context",
]


def _model_badge(kind: str, available: bool) -> tuple[str, str]:
    """Return (label, color) for the model status pill."""
    if not available:
        return ("No model – upscale disabled", COLORS["danger"])
    if kind == "smoke":
        return ("Smoke Identity (not Real-ESRGAN)", COLORS["warn"])
    if kind == "realesrgan":
        return ("Real-ESRGAN ✓", COLORS["accent"])
    if kind == "resize":
        return ("2× resize ONNX (test weights)", COLORS["warn"])
    return ("ONNX model found", COLORS["accent"])


def _duration_label(secs: float) -> str:
    m = int(secs // 60)
    s = int(secs % 60)
    h = m // 60
    m = m % 60
    if h:
        return f"{h}h {m:02d}m {s:02d}s"
    if m:
        return f"{m}m {s:02d}s"
    return f"{s}s"


def upscale_onboarding_dialog(
    ctx: OnboardingContext,
    *,
    on_proceed: Any,
    on_split: Any,
    on_cancel: Any,
) -> ft.AlertDialog:
    """Build and return the pre-upscale onboarding AlertDialog.

    The dialog is NOT automatically opened — the caller must add it to
    ``page.overlay`` and set ``page.dialog = dlg`` then ``dlg.open = True``.
    """

    model_label, model_color = _model_badge(ctx.model_kind, ctx.model_available)

    # ── Source info row ──────────────────────────────────────────────────────
    info_rows: list[ft.Control] = [
        ft.Row([
            ft.Text("Source:", weight=ft.FontWeight.BOLD, width=130, color=COLORS["text_secondary"]),
            ft.Text(ctx.source_name, color=COLORS["text_primary"], selectable=True, expand=True),
        ]),
        ft.Row([
            ft.Text("Resolution:", weight=ft.FontWeight.BOLD, width=130, color=COLORS["text_secondary"]),
            ft.Text(f"{ctx.width} × {ctx.height}", color=COLORS["text_primary"]),
        ]),
        ft.Row([
            ft.Text("Duration:", weight=ft.FontWeight.BOLD, width=130, color=COLORS["text_secondary"]),
            ft.Text(_duration_label(ctx.duration_sec), color=COLORS["text_primary"]),
        ]),
        ft.Row([
            ft.Text("Total frames:", weight=ft.FontWeight.BOLD, width=130, color=COLORS["text_secondary"]),
            ft.Text(f"{ctx.total_frames:,}", color=COLORS["text_primary"]),
        ]),
    ]

    # ── Model status ─────────────────────────────────────────────────────────
    model_rows: list[ft.Control] = [
        ft.Row([
            ft.Text("AI model:", weight=ft.FontWeight.BOLD, width=130, color=COLORS["text_secondary"]),
            ft.Text(model_label, color=model_color),
        ]),
    ]
    if ctx.model_kind == "smoke":
        model_rows.append(
            ft.Text(
                "Only a smoke/identity ONNX is present — output will use 2× interpolation, "
                "not Real-ESRGAN quality.  Run: python .\\scripts\\download_models.py",
                color=COLORS["warn"],
                size=12,
            )
        )
    elif not ctx.model_available:
        model_rows.append(
            ft.Text(
                "No ONNX model found.  Create a smoke model (not Real-ESRGAN) or run "
                "python .\\scripts\\download_models.py",
                color=COLORS["danger"],
                size=12,
            )
        )

    # ── Estimate ─────────────────────────────────────────────────────────────
    probe_note = " (hardware-probed)" if ctx.probe_used else " (estimated — no probe)"
    estimate_color = COLORS["danger"] if ctx.exceeds_gate else COLORS["accent"]
    estimate_rows: list[ft.Control] = [
        ft.Row([
            ft.Text("Est. time:", weight=ft.FontWeight.BOLD, width=130, color=COLORS["text_secondary"]),
            ft.Text(
                ctx.estimate_label + probe_note,
                color=estimate_color,
                weight=ft.FontWeight.BOLD if ctx.exceeds_gate else ft.FontWeight.NORMAL,
            ),
        ]),
        ft.Row([
            ft.Text("Upscale fps:", weight=ft.FontWeight.BOLD, width=130, color=COLORS["text_secondary"]),
            ft.Text(f"{ctx.fps_estimate:.2f} fps", color=COLORS["text_secondary"]),
        ]),
    ]

    # ── Resource reading ─────────────────────────────────────────────────────
    resource_rows: list[ft.Control] = []
    if ctx.cpu_percent is not None or ctx.ram_percent is not None:
        cpu_str = f"{ctx.cpu_percent:.0f}%" if ctx.cpu_percent is not None else "n/a"
        ram_str = f"{ctx.ram_percent:.0f}%" if ctx.ram_percent is not None else "n/a"
        ram_color = COLORS["danger"] if (ctx.ram_percent or 0) >= 85 else COLORS["text_secondary"]
        resource_rows = [
            ft.Divider(height=1, color=COLORS["border"]),
            ft.Row([
                ft.Text("CPU now:", weight=ft.FontWeight.BOLD, width=130, color=COLORS["text_secondary"]),
                ft.Text(cpu_str, color=COLORS["text_secondary"]),
                ft.Text("  RAM now:", weight=ft.FontWeight.BOLD, width=90, color=COLORS["text_secondary"]),
                ft.Text(ram_str, color=ram_color),
            ]),
        ]

    # ── Gate warning ─────────────────────────────────────────────────────────
    gate_rows: list[ft.Control] = []
    if ctx.exceeds_gate:
        gate_rows = [
            ft.Divider(height=1, color=COLORS["border"]),
            ft.Container(
                bgcolor="#3a1a00",
                border_radius=6,
                padding=10,
                content=ft.Column([
                    ft.Text(
                        "⚠  Estimated time exceeds 4 hours",
                        color=COLORS["danger"],
                        weight=ft.FontWeight.BOLD,
                        size=14,
                    ),
                    ft.Text(
                        "Running the full file on an iGPU could occupy your machine "
                        "overnight with no guarantee of completion.\n\n"
                        f"Recommended: split into ~{int(ctx.segment_minutes)}-minute segments, "
                        "upscale each sequentially, then stitch back into one remastered file.",
                        color=COLORS["text_secondary"],
                        size=12,
                    ),
                ], spacing=4),
            ),
        ]

    # ── Build content column ─────────────────────────────────────────────────
    all_rows: list[ft.Control] = (
        info_rows
        + [ft.Divider(height=1, color=COLORS["border"])]
        + model_rows
        + [ft.Divider(height=1, color=COLORS["border"])]
        + estimate_rows
        + resource_rows
        + gate_rows
    )

    content = ft.Column(
        all_rows,
        spacing=6,
        width=480,
        scroll=ft.ScrollMode.AUTO,
    )

    # ── Actions ──────────────────────────────────────────────────────────────
    actions: list[ft.Control] = [
        ft.OutlinedButton(content="Cancel", on_click=lambda _e: on_cancel()),
    ]

    if ctx.model_available:
        if ctx.exceeds_gate:
            actions.append(
                ft.OutlinedButton(
                    content="Proceed anyway (not recommended)",
                    on_click=lambda _e: on_proceed(),
                    style=ft.ButtonStyle(color=COLORS["warn"]),
                )
            )
            actions.append(
                ft.FilledButton(
                    content=f"Split into {int(ctx.segment_minutes)}-min segments",
                    bgcolor=COLORS["accent"],
                    on_click=lambda _e: on_split(),
                )
            )
        else:
            actions.append(
                ft.FilledButton(
                    content="Start upscale",
                    bgcolor=COLORS["accent"],
                    on_click=lambda _e: on_proceed(),
                )
            )
    # else: only Cancel is shown (model unavailable)

    title_text = (
        "Upscale — action required"
        if ctx.exceeds_gate or not ctx.model_available
        else "Upscale preview"
    )
    title_color = COLORS["danger"] if (ctx.exceeds_gate or not ctx.model_available) else COLORS["text_primary"]

    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Text(title_text, color=title_color, weight=ft.FontWeight.BOLD),
        content=content,
        actions=actions,
        bgcolor=COLORS["surface"],
    )
    dlg.data = {
        "ctx": ctx,
        "on_proceed": on_proceed,
        "on_split": on_split,
        "on_cancel": on_cancel,
    }
    return dlg


def build_onboarding_context(
    source: Any,
    *,
    estimate: Any,
    model_status_dict: dict | None = None,
    model_status: dict | None = None,
    resource_reading: Any | None = None,
    segment_minutes: float = 15.0,
) -> OnboardingContext:
    """Convenience factory: build OnboardingContext from pipeline objects.

    Parameters
    ----------
    source:
        Path to the source video (used for display name + metrics).
    estimate:
        ``UpscaleEstimate`` from ``frameforge.upscale.estimate``.
    model_status_dict / model_status:
        Dict from ``frameforge.upscale.onnx_upscaler.model_status()``.
        Accepts either kwarg name for compatibility.
    resource_reading:
        Optional ``ResourceReading`` from the sampler; None if unavailable.
    segment_minutes:
        Minutes per segment for the split suggestion.
    """
    from frameforge.upscale.onboarding import build_onboarding_context as _build

    ms = model_status_dict or model_status or {}
    return _build(
        source,
        estimate=estimate,
        model_status_dict=ms,
        resource_reading=resource_reading,
        segment_minutes=segment_minutes,
    )
