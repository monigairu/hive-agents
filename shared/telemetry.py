"""OpenTelemetry（GenAI semantic conventions）による分散トレース（要件 F-14 基盤）。

Hive の差別化軸「エージェントの思考・協働を可視化・監査できる」を、自前ログではなく
業界標準の OTel スパンで裏取りする。OTLP エクスポータを設定すれば
Langfuse / Arize Phoenix などへそのまま流せる＝「標準で監査可能な透明性」。

挙動:
- ``OTEL_EXPORTER_OTLP_ENDPOINT`` が未設定、または opentelemetry 未インストールなら
  **完全な no-op**（本体の動作には影響しない）。
- 有効化は環境変数 ``OTEL_EXPORTER_OTLP_ENDPOINT`` を設定するだけ。
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Iterator

try:  # opentelemetry は任意依存。無ければ全機能 no-op。
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    _OTEL = True
except ImportError:  # pragma: no cover - 依存未導入時のフォールバック
    _OTEL = False

_GEN_AI_SYSTEM = "hive"
_tracer: Any = None


def setup_tracing(service_name: str) -> Any:
    """トレーサを初期化して返す（多重呼び出し安全）。無効時は None。"""
    global _tracer
    if _tracer is not None:
        return _tracer
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not (_OTEL and endpoint):
        return None

    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer(service_name)
    return _tracer


@contextmanager
def agent_span(name: str, *, operation: str, agent: str | None = None, **attrs: Any) -> Iterator[Any]:
    """GenAI 規約に沿ったスパンを開く。トレーサ無効時は None を yield して何もしない。

    Args:
        name: スパン名（例 ``"hive.implementer"``）。
        operation: ``gen_ai.operation.name``（例 ``"invoke_agent"`` / ``"execute_tool"``）。
        agent: ``gen_ai.agent.name``。
        **attrs: 追加属性（``verify.passed`` 等）。
    """
    if _tracer is None:
        yield None
        return
    with _tracer.start_as_current_span(name) as span:
        span.set_attribute("gen_ai.system", _GEN_AI_SYSTEM)
        span.set_attribute("gen_ai.operation.name", operation)
        if agent:
            span.set_attribute("gen_ai.agent.name", agent)
        for key, value in attrs.items():
            span.set_attribute(key, value)
        try:
            yield span
        except Exception as exc:  # スパンに記録して再送出（握り潰さない）
            span.record_exception(exc)
            raise
