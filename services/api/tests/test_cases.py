from datetime import UTC, datetime, timedelta

from sawtai.cases.service import STATUS_TRANSITIONS, sla_state


def test_sla_state_is_computed_server_side() -> None:
    now = datetime(2026, 8, 12, 12, tzinfo=UTC)
    assert sla_state("assigned", now - timedelta(seconds=1), now) == "breached"
    assert sla_state("assigned", now + timedelta(hours=2), now) == "due_soon"
    assert sla_state("assigned", now + timedelta(hours=8), now) == "on_track"
    assert sla_state("resolved", now - timedelta(hours=2), now) == "completed"
    assert sla_state("new", None, now) == "not_set"


def test_case_transition_graph_has_terminal_and_reopen_rules() -> None:
    assert "triaged" in STATUS_TRANSITIONS["new"]
    assert "resolved" in STATUS_TRANSITIONS["responded"]
    assert STATUS_TRANSITIONS["closed"] == set()
    assert STATUS_TRANSITIONS["rejected"] == set()
    assert STATUS_TRANSITIONS["resolved"] == {"assigned", "closed"}
