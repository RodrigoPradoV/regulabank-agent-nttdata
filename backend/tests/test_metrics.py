"""Agregacion del ledger para el dashboard de trazabilidad (agents/metrics.py)."""

from __future__ import annotations

from regulabank.agents import metrics

ENTRIES = [
    {
        "logged_at": "2026-10-15T10:00:00+00:00", "question": "umbral de concentracion", "as_of": "2026-10-15",
        "scenario": "threshold", "status": "ok", "risk": "auto", "latency_ms": 900, "fixes": 0,
        "faults": [], "human_decision": None, "model": "mock", "seen": ["c_1"],
    },
    {
        "logged_at": "2026-10-15T11:00:00+00:00", "question": "criptoactivos en banca", "as_of": "2026-10-15",
        "scenario": "negative", "status": "abstained", "risk": None, "latency_ms": 500, "fixes": 0,
        "faults": [], "human_decision": None, "model": "mock", "seen": [],
    },
    {
        "logged_at": "2026-10-16T09:00:00+00:00", "question": "politica vs circular de liquidez",
        "as_of": "2026-10-16", "scenario": "policy_vs_norm", "status": "ok", "risk": "approve",
        "latency_ms": 2100, "fixes": 1, "faults": ["foreign_fact"], "human_decision": "accept",
        "model": "mock", "seen": ["c_2", "c_3"],
    },
    {
        "logged_at": "2026-10-16T12:00:00+00:00", "question": "circular derogada de provisiones",
        "as_of": "2026-10-16", "scenario": "procedure", "status": "rejected", "risk": None,
        "latency_ms": 1800, "fixes": 2, "faults": ["quote_missing", "quote_missing"],
        "human_decision": None, "model": "mock", "seen": ["c_4"],
    },
]


def test_summarize_counts_and_rates() -> None:
    summary = metrics.summarize(ENTRIES)

    assert summary["total"] == 4
    assert summary["by_status"] == {"ok": 2, "abstained": 1, "rejected": 1}
    assert summary["human_review_rate"] == 0.25  # una de cuatro con risk=approve
    assert summary["fault_counts"] == {"foreign_fact": 1, "quote_missing": 2}
    assert summary["fixes_histogram"] == {"0": 2, "1": 1, "2": 1}


def test_summarize_latency_percentiles() -> None:
    summary = metrics.summarize(ENTRIES)

    assert summary["latency_ms_avg"] == sum(e["latency_ms"] for e in ENTRIES) / 4
    assert summary["latency_ms_p95"] >= summary["latency_ms_p50"] >= 0


def test_summarize_time_saved_only_counts_autonomous_runs() -> None:
    summary = metrics.summarize(ENTRIES)

    # Solo "ok" (900ms) y "abstained" (500ms) cuentan; "rejected" no, aunque tambien tuvo latencia.
    expected = (metrics.HUMAN_BASELINE_MINUTES - 900 / 60_000) + (metrics.HUMAN_BASELINE_MINUTES - 500 / 60_000)
    assert round(summary["time_saved_minutes"], 4) == round(expected, 4)


def test_daily_series_groups_by_day() -> None:
    series = metrics.daily_series(ENTRIES)

    assert [point["bucket"] for point in series] == ["2026-10-15", "2026-10-16"]
    assert series[0]["count"] == 2
    assert series[0]["abstained"] == 1
    assert series[1]["count"] == 2
    assert series[1]["rejected"] == 1


def test_filter_entries_combines_filters() -> None:
    filters = metrics.MetricsFilters(scenario="threshold")
    assert len(metrics.filter_entries(ENTRIES, filters)) == 1

    filters = metrics.MetricsFilters(status="ok", date_from="2026-10-16")
    out = metrics.filter_entries(ENTRIES, filters)
    assert len(out) == 1
    assert out[0]["question"] == "politica vs circular de liquidez"

    filters = metrics.MetricsFilters(q="liquidez")
    out = metrics.filter_entries(ENTRIES, filters)
    assert len(out) == 1
    assert out[0]["scenario"] == "policy_vs_norm"


def test_load_returns_empty_list_when_ledger_file_is_missing(tmp_path) -> None:
    assert metrics.load(tmp_path / "no_existe.jsonl") == []
