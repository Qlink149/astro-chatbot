"""Shared pytest fixtures."""

import pytest


@pytest.fixture(autouse=True)
def disable_kisna_utms_in_tests(monkeypatch):
    """Keep legacy URL assertions stable; UTM behavior tested separately."""
    monkeypatch.setenv("KISNA_UTM_ENABLED", "false")


class _NoopCollection:
    """Swallows funnel writes; each real one blocks ~30s without a Mongo server."""

    def update_one(self, *args, **kwargs):
        return None


@pytest.fixture(autouse=True)
def stub_funnel_writes(monkeypatch):
    """Funnel counters are best-effort telemetry — never a test dependency.

    Event-name validation still runs, so an unregistered event still warns.
    """
    import kisna_chatbot.utils.funnel_events as fe

    monkeypatch.setattr(fe, "samara_funnel", _NoopCollection(), raising=False)
