"""Parser for MercadoLibre operational KPI tables from SEC earnings releases."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Final

from bs4 import BeautifulSoup


SUMMARY_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"The following table summarizes certain key performance metrics "
    r"for the (?P<period_phrase>.+?) periods? ended "
    r"(?P<month>March|June|September|December)\s+"
    r"(?P<day>\d{1,2}),\s+"
    r"(?P<year>\d{4})\s+and\s+"
    r"(?P<prior_year>\d{4})",
    flags=re.IGNORECASE,
)

NUMBER_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\$?\s*"
    r"(?P<number>\(?-?\d[\d,]*(?:\.\d+)?\)?)"
    r"\s*(?P<percent>%?)"
)


@dataclass(frozen=True)
class MetricSpec:
    metric_id: str
    source_label: str
    unit: str
    scale_factor: int


@dataclass(frozen=True)
class ColumnSpec:
    reference_year: int
    period_start: date
    period_end: date
    period_type: str
    period_label: str
    is_comparative: bool


METRICS: Final[tuple[MetricSpec, ...]] = (
    MetricSpec(
        metric_id="fintech_mau",
        source_label="Fintech monthly active users",
        unit="users",
        scale_factor=1_000_000,
    ),
    MetricSpec(
        metric_id="unique_active_buyers",
        source_label="Unique active buyers",
        unit="users",
        scale_factor=1_000_000,
    ),
    MetricSpec(
        metric_id="gmv",
        source_label="Gross merchandise volume",
        unit="USD",
        scale_factor=1_000_000,
    ),
    MetricSpec(
        metric_id="items_sold",
        source_label="Number of items sold",
        unit="items",
        scale_factor=1_000_000,
    ),
    MetricSpec(
        metric_id="tpv",
        source_label="Total payment volume",
        unit="USD",
        scale_factor=1_000_000,
    ),
    MetricSpec(
        metric_id="acquiring_tpv",
        source_label="Acquiring total payment volume",
        unit="USD",
        scale_factor=1_000_000,
    ),
    MetricSpec(
        metric_id="payment_transactions",
        source_label="Total payment transactions",
        unit="transactions",
        scale_factor=1_000_000,
    ),
    MetricSpec(
        metric_id="nimal",
        source_label="NIMAL",
        unit="percent",
        scale_factor=1,
    ),
)


MONTH_NUMBER: Final[dict[str, int]] = {
    "march": 3,
    "june": 6,
    "september": 9,
    "december": 12,
}


def html_to_normalized_text(
    content: bytes | str,
) -> str:
    """Flatten Workiva presentation HTML into deterministic text."""
    soup = BeautifulSoup(
        content,
        "html.parser",
    )

    text = soup.get_text(
        " ",
        strip=True,
    )

    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


def _parse_reported_number(
    value: str,
) -> float:
    normalized = (
        value
        .replace(",", "")
        .strip()
    )

    negative = (
        normalized.startswith("(")
        and normalized.endswith(")")
    )

    if negative:
        normalized = normalized[1:-1]

    parsed = float(normalized)

    if negative:
        parsed *= -1

    return parsed


def _period_columns(
    *,
    month: int,
    day: int,
    year: int,
    prior_year: int,
) -> list[ColumnSpec]:
    current_end = date(
        year,
        month,
        day,
    )

    prior_end = date(
        prior_year,
        month,
        day,
    )

    def column(
        reference_year: int,
        *,
        start_month: int,
        start_day: int,
        end: date,
        period_type: str,
        period_label: str,
        comparative: bool,
    ) -> ColumnSpec:
        return ColumnSpec(
            reference_year=reference_year,
            period_start=date(
                reference_year,
                start_month,
                start_day,
            ),
            period_end=end,
            period_type=period_type,
            period_label=period_label,
            is_comparative=comparative,
        )

    if month == 3:
        return [
            column(
                year,
                start_month=1,
                start_day=1,
                end=current_end,
                period_type="QUARTER",
                period_label="Q1",
                comparative=False,
            ),
            column(
                prior_year,
                start_month=1,
                start_day=1,
                end=prior_end,
                period_type="QUARTER",
                period_label="Q1",
                comparative=True,
            ),
        ]

    if month == 6:
        return [
            column(
                year,
                start_month=1,
                start_day=1,
                end=current_end,
                period_type="YTD",
                period_label="H1",
                comparative=False,
            ),
            column(
                prior_year,
                start_month=1,
                start_day=1,
                end=prior_end,
                period_type="YTD",
                period_label="H1",
                comparative=True,
            ),
            column(
                year,
                start_month=4,
                start_day=1,
                end=current_end,
                period_type="QUARTER",
                period_label="Q2",
                comparative=False,
            ),
            column(
                prior_year,
                start_month=4,
                start_day=1,
                end=prior_end,
                period_type="QUARTER",
                period_label="Q2",
                comparative=True,
            ),
        ]

    if month == 9:
        return [
            column(
                year,
                start_month=1,
                start_day=1,
                end=current_end,
                period_type="YTD",
                period_label="9M",
                comparative=False,
            ),
            column(
                prior_year,
                start_month=1,
                start_day=1,
                end=prior_end,
                period_type="YTD",
                period_label="9M",
                comparative=True,
            ),
            column(
                year,
                start_month=7,
                start_day=1,
                end=current_end,
                period_type="QUARTER",
                period_label="Q3",
                comparative=False,
            ),
            column(
                prior_year,
                start_month=7,
                start_day=1,
                end=prior_end,
                period_type="QUARTER",
                period_label="Q3",
                comparative=True,
            ),
        ]

    if month == 12:
        return [
            column(
                year,
                start_month=1,
                start_day=1,
                end=current_end,
                period_type="FY",
                period_label="FY",
                comparative=False,
            ),
            column(
                prior_year,
                start_month=1,
                start_day=1,
                end=prior_end,
                period_type="FY",
                period_label="FY",
                comparative=True,
            ),
            column(
                year,
                start_month=10,
                start_day=1,
                end=current_end,
                period_type="QUARTER",
                period_label="Q4",
                comparative=False,
            ),
            column(
                prior_year,
                start_month=10,
                start_day=1,
                end=prior_end,
                period_type="QUARTER",
                period_label="Q4",
                comparative=True,
            ),
        ]

    raise ValueError(
        f"Unsupported operational period month: {month}"
    )


def _quarter_label(
    month: int,
) -> str:
    mapping = {
        3: "Q1",
        6: "Q2",
        9: "Q3",
        12: "Q4",
    }

    try:
        return mapping[month]
    except KeyError as exc:
        raise ValueError(
            f"Unsupported quarter-end month: {month}"
        ) from exc


def _extract_metric_block(
    text: str,
    summary_end: int,
) -> str:
    start = text.lower().find(
        "fintech monthly active users",
        summary_end,
    )

    if start < 0:
        raise ValueError(
            "Operational KPI table start not found."
        )

    end = text.lower().find(
        "capital expenditures",
        start,
    )

    if end < 0:
        raise ValueError(
            "Operational KPI table end not found."
        )

    return text[start:end]


def _metric_segments(
    block: str,
) -> dict[str, str]:
    matches: list[
        tuple[MetricSpec, re.Match[str]]
    ] = []

    search_start = 0

    for metric in METRICS:
        pattern = re.compile(
            re.escape(
                metric.source_label
            )
            + r"(?:\s*\(\d+\))?",
            flags=re.IGNORECASE,
        )

        match = pattern.search(
            block,
            search_start,
        )

        if match is None:
            raise ValueError(
                "Metric not found in operational KPI block: "
                f"{metric.source_label}"
            )

        matches.append(
            (
                metric,
                match,
            )
        )

        search_start = match.end()

    result: dict[str, str] = {}

    for index, (
        metric,
        match,
    ) in enumerate(matches):
        if index + 1 < len(matches):
            end = matches[index + 1][
                1
            ].start()
        else:
            end = len(block)

        result[metric.metric_id] = (
            block[
                match.end():end
            ].strip()
        )

    return result


def _extract_values(
    segment: str,
    expected_count: int,
) -> list[float]:
    values = [
        _parse_reported_number(
            match.group("number")
        )
        for match in NUMBER_PATTERN.finditer(
            segment
        )
    ]

    if len(values) != expected_count:
        raise ValueError(
            "Unexpected number of KPI values. "
            f"Expected {expected_count}, "
            f"found {len(values)} in: {segment!r}"
        )

    return values


def _definition_version(
    metric_id: str,
    *,
    period_start: date | None,
    period_end: date,
    full_text: str,
) -> str:
    text = full_text.lower()

    if metric_id in {
        "unique_active_buyers",
        "gmv",
        "items_sold",
    }:
        change_date = date(
            2025,
            4,
            1,
        )

        first_changed_period_end = date(
            2025,
            6,
            30,
        )

        if period_end < first_changed_period_end:
            return "v1_marketplace_only"

        # H1, 9M and FY 2025 start before the Q2'25
        # definition change and therefore contain a mixture
        # of pre-change and post-change periods.
        if (
            period_start is not None
            and period_start < change_date
            and period_end >= first_changed_period_end
        ):
            return (
                "v2_food_delivery_transition_2025"
            )

        return "v2_food_delivery"

    if metric_id == "fintech_mau":
        if period_end >= date(
            2026,
            3,
            31,
        ):
            return (
                "v2_active_policy_and_current_loan"
            )

        return "v1_transaction_action"

    if metric_id in {
        "tpv",
        "payment_transactions",
    }:
        if period_end.year >= 2024:
            return "v2_excludes_p2p"

        recast_marker = (
            "have been recast to exclude "
            "peer-to-peer transactions"
        )

        if (
            period_end.year == 2023
            and recast_marker in text
        ):
            return (
                "v2_recast_excludes_p2p"
            )

        return "v1_includes_p2p"

    return "v1"

def _scaled_value(
    reported_value: float,
    metric: MetricSpec,
) -> int | float:
    if metric.unit == "percent":
        return float(
            reported_value
        )

    return int(
        round(
            reported_value
            * metric.scale_factor
        )
    )


def _base_row(
    *,
    metric: MetricSpec,
    reported_value: float,
    period_start: date | None,
    period_end: date,
    reference_year: int,
    period_type: str,
    period_label: str,
    is_comparative: bool,
    definition_version: str,
    release_reference_period: date,
    metadata: dict,
) -> dict:
    return {
        "metric_id": metric.metric_id,
        "source_label": (
            metric.source_label
        ),
        "reported_value": (
            reported_value
        ),
        "reported_scale": (
            "percent"
            if metric.unit == "percent"
            else "millions"
        ),
        "value": _scaled_value(
            reported_value,
            metric,
        ),
        "unit": metric.unit,
        "period_start": (
            period_start.isoformat()
            if period_start is not None
            else None
        ),
        "period_end": (
            period_end.isoformat()
        ),
        "reference_year": (
            reference_year
        ),
        "period_type": period_type,
        "period_label": period_label,
        "definition_version": (
            definition_version
        ),
        "is_comparative": (
            is_comparative
        ),
        "release_reference_period": (
            release_reference_period.isoformat()
        ),
        "filing_date": metadata.get(
            "filing_date"
        ),
        "sec_report_date": metadata.get(
            "sec_report_date"
        ),
        "accession_number": metadata.get(
            "accession_number"
        ),
        "source_url": metadata.get(
            "source_url"
        ),
        "source": (
            metadata.get("source")
            or "SEC EDGAR earnings release"
        ),
    }


def parse_operational_release(
    content: bytes | str,
    metadata: dict,
) -> list[dict]:
    """Parse the eight recurring operational KPIs from one release."""
    text = html_to_normalized_text(
        content
    )

    summary = SUMMARY_PATTERN.search(
        text
    )

    if summary is None:
        raise ValueError(
            "Operational KPI summary statement not found."
        )

    month_name = (
        summary.group("month")
        .lower()
    )

    month = MONTH_NUMBER[
        month_name
    ]

    day = int(
        summary.group("day")
    )

    year = int(
        summary.group("year")
    )

    prior_year = int(
        summary.group("prior_year")
    )

    if prior_year != year - 1:
        raise ValueError(
            "Operational comparative year is not the "
            "immediately preceding year."
        )

    release_reference_period = date(
        year,
        month,
        day,
    )

    columns = _period_columns(
        month=month,
        day=day,
        year=year,
        prior_year=prior_year,
    )

    block = _extract_metric_block(
        text,
        summary.end(),
    )

    segments = _metric_segments(
        block
    )

    rows: list[dict] = []

    for metric in METRICS:
        values = _extract_values(
            segments[metric.metric_id],
            len(columns),
        )

        if metric.metric_id == "fintech_mau":
            by_year: dict[
                int,
                list[
                    tuple[
                        ColumnSpec,
                        float,
                    ]
                ],
            ] = {}

            for column, value in zip(
                columns,
                values,
                strict=True,
            ):
                by_year.setdefault(
                    column.reference_year,
                    [],
                ).append(
                    (
                        column,
                        value,
                    )
                )

            for reference_year, pairs in (
                by_year.items()
            ):
                distinct_values = {
                    value
                    for _, value in pairs
                }

                if len(
                    distinct_values
                ) != 1:
                    raise ValueError(
                        "Fintech MAU duplicated table columns "
                        "do not agree for year "
                        f"{reference_year}: "
                        f"{sorted(distinct_values)}"
                    )

                column = pairs[0][0]
                reported_value = pairs[0][1]

                instant_end = date(
                    reference_year,
                    month,
                    day,
                )

                rows.append(
                    _base_row(
                        metric=metric,
                        reported_value=(
                            reported_value
                        ),
                        period_start=None,
                        period_end=instant_end,
                        reference_year=(
                            reference_year
                        ),
                        period_type="INSTANT",
                        period_label=(
                            _quarter_label(
                                month
                            )
                        ),
                        is_comparative=(
                            column.is_comparative
                        ),
                        definition_version=(
                            _definition_version(
                                metric.metric_id,
                                period_start=None,
                                period_end=instant_end,
                                full_text=text,
                            )
                        ),
                        release_reference_period=(
                            release_reference_period
                        ),
                        metadata=metadata,
                    )
                )

            continue

        for column, reported_value in zip(
            columns,
            values,
            strict=True,
        ):
            rows.append(
                _base_row(
                    metric=metric,
                    reported_value=(
                        reported_value
                    ),
                    period_start=(
                        column.period_start
                    ),
                    period_end=(
                        column.period_end
                    ),
                    reference_year=(
                        column.reference_year
                    ),
                    period_type=(
                        column.period_type
                    ),
                    period_label=(
                        column.period_label
                    ),
                    is_comparative=(
                        column.is_comparative
                    ),
                    definition_version=(
                        _definition_version(
                            metric.metric_id,
                            period_start=(
                                column.period_start
                            ),
                            period_end=(
                                column.period_end
                            ),
                            full_text=text,
                        )
                    ),
                    release_reference_period=(
                        release_reference_period
                    ),
                    metadata=metadata,
                )
            )

    return rows