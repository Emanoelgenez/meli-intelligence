"""Structured extended KPIs and narrative evidence from earnings releases."""

from __future__ import annotations

import hashlib
import re
from datetime import date
from typing import Final

from meli_intelligence.transformations.operational_kpis import (
    html_to_normalized_text,
    parse_operational_release,
)


AUM_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(
        r"AUM has grown from \$[\d.]+bn to "
        r"(?P<approx>almost\s+)?"
        r"\$(?P<value>[\d.]+)bn",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"AUM.{0,260}?"
        r"(?:"
        r"reached"
        r"|"
        r"(?:grew|doubling)[^$]{0,120}?to"
        r")\s+"
        r"(?P<approx>almost\s+)?"
        r"\$(?P<value>[\d.]+)bn",
        flags=re.IGNORECASE,
    ),
)

CREDIT_PORTFOLIO_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?:total\s+)?credit portfolio"
    r".{0,320}?"
    r"\$(?P<value>[\d.]+)bn",
    flags=re.IGNORECASE,
)

NPL_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(
        r"15-90 day NPL of "
        r"(?P<value>\d+(?:\.\d+)?)% "
        r"for the portfolio as a whole",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"15-90 day NPL was "
        r"(?P<value>\d+(?:\.\d+)?)% "
        r"for the portfolio as a whole",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"Our 15-90 day NPL ratio improved to "
        r"(?P<value>\d+(?:\.\d+)?)%",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"The 15-90 day NPL remained stable at "
        r"(?P<value>\d+(?:\.\d+)?)%",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"with the 15-90 day NPL broadly stable QoQ at "
        r"(?P<value>\d+(?:\.\d+)?)%",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"with the 15-90 day NPL of "
        r"(?P<value>\d+(?:\.\d+)?)% "
        r"broadly stable YoY",
        flags=re.IGNORECASE,
    ),
)


EVIDENCE_CONFIG: Final[dict[str, dict]] = {
    "meli_plus": {
        "business_domain": "Ecosystem",
        "patterns": (
            re.compile(
                r"\bMELI\+",
                flags=re.IGNORECASE,
            ),
        ),
    },
    "ecosystemic_users": {
        "business_domain": "Ecosystem",
        "patterns": (
            re.compile(
                r"\becosystemic users?\b",
                flags=re.IGNORECASE,
            ),
        ),
    },
    "advertising": {
        "business_domain": "Ads",
        "patterns": (
            re.compile(
                r"\badvertising\b",
                flags=re.IGNORECASE,
            ),
            re.compile(
                r"\bAds revenue\b",
                flags=re.IGNORECASE,
            ),
            re.compile(
                r"\bdigital advertising market\b",
                flags=re.IGNORECASE,
            ),
        ),
    },
    "fulfillment": {
        "business_domain": "Logistics",
        "patterns": (
            re.compile(
                r"\bfulfillment\b",
                flags=re.IGNORECASE,
            ),
        ),
    },
}


def _reference_period(
    content: bytes | str,
    metadata: dict,
    reference_period: str | date | None,
) -> date:
    if isinstance(
        reference_period,
        date,
    ):
        return reference_period

    if isinstance(
        reference_period,
        str,
    ):
        return date.fromisoformat(
            reference_period
        )

    rows = parse_operational_release(
        content,
        metadata,
    )

    periods = {
        row["release_reference_period"]
        for row in rows
    }

    if len(periods) != 1:
        raise ValueError(
            "Unable to resolve one release reference period."
        )

    return date.fromisoformat(
        periods.pop()
    )


def _quarter_label(
    period_end: date,
) -> str:
    labels = {
        3: "Q1",
        6: "Q2",
        9: "Q3",
        12: "Q4",
    }

    try:
        return labels[
            period_end.month
        ]
    except KeyError as exc:
        raise ValueError(
            "Unsupported quarter-end month."
        ) from exc


def _source_text(
    text: str,
    start: int,
    end: int,
) -> str:
    left = text.rfind(
        ". ",
        0,
        start,
    )

    if left < 0:
        left = max(
            0,
            start - 250,
        )
    else:
        left += 2

    right = text.find(
        ". ",
        end,
    )

    if right < 0:
        right = min(
            len(text),
            end + 350,
        )
    else:
        right += 1

    return text[
        left:right
    ].strip()


def _fact(
    *,
    metric_id: str,
    reported_value: float,
    reported_scale: str,
    value: float,
    unit: str,
    qualifier: str,
    definition_version: str,
    period_end: date,
    source_text: str,
    metadata: dict,
) -> dict:
    return {
        "metric_id": metric_id,
        "scope": "total_portfolio"
        if metric_id in {
            "credit_portfolio",
            "npl_15_90_total",
        }
        else "total",
        "reported_value": float(
            reported_value
        ),
        "reported_scale": (
            reported_scale
        ),
        "value": float(
            value
        ),
        "unit": unit,
        "value_qualifier": (
            qualifier
        ),
        "period_start": None,
        "period_end": (
            period_end.isoformat()
        ),
        "reference_year": (
            period_end.year
        ),
        "period_type": "INSTANT",
        "period_label": (
            _quarter_label(
                period_end
            )
        ),
        "definition_version": (
            definition_version
        ),
        "source_text": source_text,
        "filing_date": metadata.get(
            "filing_date"
        ),
        "accession_number": metadata.get(
            "accession_number"
        ),
        "source_url": metadata.get(
            "source_url"
        ),
        "source": (
            metadata.get("source")
            or "SEC EDGAR earnings release exhibit"
        ),
    }


def _extract_aum(
    text: str,
    period_end: date,
    metadata: dict,
) -> dict | None:
    for pattern in AUM_PATTERNS:
        match = pattern.search(
            text
        )

        if match is None:
            continue

        reported = float(
            match.group("value")
        )

        qualifier = (
            "approximate"
            if match.groupdict().get(
                "approx"
            )
            else "exact"
        )

        return _fact(
            metric_id="aum",
            reported_value=reported,
            reported_scale="billions",
            value=reported * 1_000_000_000,
            unit="USD",
            qualifier=qualifier,
            definition_version="v1",
            period_end=period_end,
            source_text=_source_text(
                text,
                match.start(),
                match.end(),
            ),
            metadata=metadata,
        )

    return None


def _extract_credit_portfolio(
    text: str,
    period_end: date,
    metadata: dict,
) -> dict | None:
    match = (
        CREDIT_PORTFOLIO_PATTERN
        .search(text)
    )

    if match is None:
        return None

    reported = float(
        match.group("value")
    )

    dollar_position = text.find(
        "$",
        match.start(),
        match.end(),
    )

    preceding = text[
        max(
            match.start(),
            dollar_position - 70,
        ):
        dollar_position
    ].lower()

    qualifier = (
        "lower_bound"
        if any(
            token in preceding
            for token in (
                "surpassed",
                "exceeds",
                "more than",
            )
        )
        else "exact"
    )

    return _fact(
        metric_id="credit_portfolio",
        reported_value=reported,
        reported_scale="billions",
        value=reported * 1_000_000_000,
        unit="USD",
        qualifier=qualifier,
        definition_version="v1_total_credit_portfolio",
        period_end=period_end,
        source_text=_source_text(
            text,
            match.start(),
            match.end(),
        ),
        metadata=metadata,
    )


def _extract_npl(
    text: str,
    period_end: date,
    metadata: dict,
) -> dict | None:
    for pattern in NPL_PATTERNS:
        match = pattern.search(
            text
        )

        if match is None:
            continue

        reported = float(
            match.group("value")
        )

        return _fact(
            metric_id="npl_15_90_total",
            reported_value=reported,
            reported_scale="percent",
            value=reported,
            unit="percent",
            qualifier="exact",
            definition_version=(
                "v1_15_90_total_portfolio"
            ),
            period_end=period_end,
            source_text=_source_text(
                text,
                match.start(),
                match.end(),
            ),
            metadata=metadata,
        )

    return None


def _sentences(
    text: str,
) -> list[str]:
    return [
        sentence.strip()
        for sentence in re.split(
            r"(?<=[.!?])\s+(?=[A-Z0-9])",
            text,
        )
        if sentence.strip()
    ]


def _evidence_id(
    accession_number: str,
    reference_period: date,
    evidence_type: str,
    statement: str,
) -> str:
    raw = (
        f"{accession_number}|"
        f"{reference_period.isoformat()}|"
        f"{evidence_type}|"
        f"{statement}"
    ).encode(
        "utf-8"
    )

    return hashlib.sha256(
        raw
    ).hexdigest()[:24]


def _extract_evidence(
    text: str,
    period_end: date,
    metadata: dict,
) -> list[dict]:
    sentences = _sentences(
        text
    )

    rows = []

    for evidence_type, config in (
        EVIDENCE_CONFIG.items()
    ):
        selected: list[str] = []

        for sentence in sentences:
            if not any(
                pattern.search(
                    sentence
                )
                for pattern in config[
                    "patterns"
                ]
            ):
                continue

            # Keep factual/operational statements rather
            # than every generic mention of a topic.
            signal = bool(
                re.search(
                    r"\d|growth|grow|grew|growing|volume|"
                    r"share|revenue|subscriber|users?|"
                    r"GMV|TPV|shipping|delivery|"
                    r"penetration|cost|market",
                    sentence,
                    flags=re.IGNORECASE,
                )
            )

            if not signal:
                continue

            normalized = re.sub(
                r"\s+",
                " ",
                sentence,
            ).strip()

            if normalized in selected:
                continue

            selected.append(
                normalized
            )

            if len(
                selected
            ) >= 3:
                break

        for statement in selected:
            accession = str(
                metadata.get(
                    "accession_number"
                )
                or ""
            )

            rows.append(
                {
                    "evidence_id": (
                        _evidence_id(
                            accession,
                            period_end,
                            evidence_type,
                            statement,
                        )
                    ),
                    "evidence_class": "FACT",
                    "evidence_type": (
                        evidence_type
                    ),
                    "business_domain": (
                        config[
                            "business_domain"
                        ]
                    ),
                    "reference_period": (
                        period_end.isoformat()
                    ),
                    "reference_year": (
                        period_end.year
                    ),
                    "statement": (
                        statement
                    ),
                    "has_numeric_signal": bool(
                        re.search(
                            r"\d",
                            statement,
                        )
                    ),
                    "filing_date": (
                        metadata.get(
                            "filing_date"
                        )
                    ),
                    "accession_number": (
                        accession
                    ),
                    "source_url": (
                        metadata.get(
                            "source_url"
                        )
                    ),
                    "source": (
                        metadata.get(
                            "source"
                        )
                        or (
                            "SEC EDGAR earnings "
                            "release exhibit"
                        )
                    ),
                }
            )

    return rows


def parse_extended_release(
    content: bytes | str,
    metadata: dict,
    *,
    reference_period: str | date | None = None,
) -> tuple[list[dict], list[dict]]:
    """Extract structured extended KPIs and evidence facts."""
    text = html_to_normalized_text(
        content
    )

    period_end = _reference_period(
        content,
        metadata,
        reference_period,
    )

    facts = []

    for extractor in (
        _extract_aum,
        _extract_credit_portfolio,
        _extract_npl,
    ):
        row = extractor(
            text,
            period_end,
            metadata,
        )

        if row is not None:
            facts.append(
                row
            )

    evidence = _extract_evidence(
        text,
        period_end,
        metadata,
    )

    return (
        facts,
        evidence,
    )