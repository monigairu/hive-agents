"""shared/telemetry.py の単体テスト（OTel無効時の no-op を保証）。"""

from __future__ import annotations

import pytest

from shared import telemetry


def test_setup_tracing_noop_without_endpoint(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.setattr(telemetry, "_tracer", None)
    assert telemetry.setup_tracing("hive-test") is None


def test_agent_span_noop_yields_none():
    telemetry._tracer = None
    with telemetry.agent_span("hive.test", operation="invoke_agent", agent="x") as span:
        assert span is None


def test_agent_span_does_not_swallow_exceptions():
    telemetry._tracer = None
    with pytest.raises(ValueError):
        with telemetry.agent_span("hive.test", operation="invoke_agent"):
            raise ValueError("boom")
