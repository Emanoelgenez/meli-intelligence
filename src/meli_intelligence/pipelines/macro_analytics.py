"""Orchestrate pure Macro analytics, observations, and Gold persistence."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from meli_intelligence.analytics.macro import build_macro_analytics
from meli_intelligence.analytics.macro_evidence import build_macro_observations
from meli_intelligence.storage.macro_analytics import (
    DEFAULT_MACRO_ANALYTICS_PATH,
    DEFAULT_MACRO_EVIDENCE_PATH,
    write_macro_analytics,
    write_macro_evidence,
)


def build_macro_gold(
    macro_silver: pd.DataFrame,
    *,
    analytics_path: Path = DEFAULT_MACRO_ANALYTICS_PATH,
    evidence_path: Path = DEFAULT_MACRO_EVIDENCE_PATH,
) -> tuple[pd.DataFrame, pd.DataFrame, tuple[Path, Path], tuple[Path, Path]]:
    """Build derived analytics and observations, then write separate Gold files."""
    analytics = build_macro_analytics(macro_silver)
    if analytics.empty:
        raise ValueError("No comparable Macro periods exist for derived analytics.")
    observations = build_macro_observations(macro_silver, analytics)
    analytics_files = write_macro_analytics(analytics, path=analytics_path)
    evidence_files = write_macro_evidence(observations, path=evidence_path)
    return analytics, observations, analytics_files, evidence_files
