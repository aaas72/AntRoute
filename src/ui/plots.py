# -*- coding: utf-8 -*-
"""
src/ui/plots.py

Plotly grafikleri:
  - convergence_figure     : ACO yakınsama grafiği (en iyi / ortalama / en kötü)
  - distance_heatmap_figure: maliyet matrisinin ısı haritası
  - comparison_figure      : algoritma karşılaştırma çubuk grafiği
"""

from __future__ import annotations

from typing import Dict, List, Sequence

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

SERIES = {
    "best_distance": ("En iyi (şimdiye kadar)", "#d63a2f", 3),
    "average_distance": ("İterasyon ortalaması", "#1f5fbf", 1.5),
    "worst_distance": ("İterasyonun en kötüsü", "#9aa3ad", 1),
}


def convergence_figure(history: List[Dict], unit: str = "km") -> go.Figure:
    df = pd.DataFrame(history)
    fig = go.Figure()
    for col in ("worst_distance", "average_distance", "best_distance"):
        label, color, width = SERIES[col]
        fig.add_trace(go.Scatter(
            x=df["iteration"], y=df[col], name=label, mode="lines",
            line={"color": color, "width": width},
            hovertemplate=f"%{{y:.2f}} {unit}<extra>{label}</extra>",
        ))
    fig.update_layout(
        xaxis_title="İterasyon", yaxis_title=f"Rota maliyeti ({unit})",
        hovermode="x unified", legend={"orientation": "h", "y": 1.1},
        margin={"l": 10, "r": 10, "t": 40, "b": 10}, height=420,
    )
    return fig


def distance_heatmap_figure(matrix: np.ndarray, names: Sequence[str], unit: str = "km") -> go.Figure:
    z = np.where(np.isfinite(matrix), matrix, np.nan)
    short = [n if len(n) <= 22 else n[:21] + "…" for n in names]
    fig = px.imshow(
        z, x=short, y=short, color_continuous_scale="Viridis",
        text_auto=".1f" if len(names) <= 15 else False,
        labels={"x": "Varış", "y": "Çıkış", "color": unit}, aspect="auto",
    )
    size = min(900, max(420, 38 * len(names) + 200))
    fig.update_layout(height=size, margin={"l": 10, "r": 10, "t": 30, "b": 10})
    fig.update_xaxes(tickangle=-45)
    return fig


def comparison_figure(rows: List[Dict], unit: str = "km") -> go.Figure:
    df = pd.DataFrame(rows)
    colors = ["#d63a2f" if "ACO" in m else "#9aa3ad" for m in df["Yöntem"]]
    fig = go.Figure(go.Bar(
        x=df["Maliyet"], y=df["Yöntem"], orientation="h", marker_color=colors,
        text=[f"{v:.2f} {unit}" for v in df["Maliyet"]], textposition="auto",
        hovertemplate=f"%{{x:.3f}} {unit}<extra></extra>",
    ))
    fig.update_layout(
        xaxis_title=f"Toplam maliyet ({unit})", yaxis={"autorange": "reversed"},
        height=80 + 50 * len(df), margin={"l": 10, "r": 10, "t": 10, "b": 10},
    )
    return fig
