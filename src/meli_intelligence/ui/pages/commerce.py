"""Commerce domain storytelling page; source facts remain in existing layers."""
from __future__ import annotations

from meli_intelligence.ui.domain_storytelling import render_domain_page
from meli_intelligence.ui.filters import FilterState


def render(st, health_records, catalog=None, filters: FilterState | None = None) -> None:
    render_domain_page(st, health_records, "Commerce", filters)
