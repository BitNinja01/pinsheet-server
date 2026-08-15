"""OpenTelemetry scaffolding for /api/v1 (ADR-003).

`init_tracing(app)` reads `OTEL_ENABLED` (env, default off) and installs
either the OTel API's no-op `TracerProvider` (disabled -- the default) or a
real SDK `TracerProvider` with **no exporter attached** (enabled). Either way
nothing leaves the process: there is no telemetry egress trust boundary in
this build (L2 -- eng-lead §L2 item 7 / eng-architect ADR-003 consequences).

`current_trace_id()` is the only function v1 code calls directly (via
`errors.problem(...)`); it must NEVER raise, so a future OTel SDK bug can
never 500 a v1 request (coding standard §4.6) -- mirrors the defensive
`try/except Exception` pattern already used for plugin teardown
(`main.py`'s `_unregister_plugins`).
"""
import logging
import os
import uuid

_log = logging.getLogger("pinsheet")


def init_tracing(app) -> None:
    """Install the OTel TracerProvider and wire a per-`/api/v1` request span.

    Defensive by design: any failure here is caught and logged, never raised,
    so a broken/absent OTel SDK can never prevent the app from serving legacy
    or v1 requests.
    """
    try:
        from opentelemetry import trace

        enabled = os.environ.get("OTEL_ENABLED", "0").lower() in ("1", "true", "yes")
        if enabled:
            from opentelemetry.sdk.trace import TracerProvider

            # EXPORTER SEAM: wire a real exporter here later, e.g.
            #   provider.add_span_processor(BatchSpanProcessor(<OTLPExporter>))
            # Adding one is a one-line change + a dependency; it touches no
            # v1 handler and no error contract. LINDDUN note: span attributes
            # MUST be reviewed for PII (user_id, course geolocation) before
            # any exporter is ever enabled.
            trace.set_tracer_provider(TracerProvider())
        # else: leave the OTel API's default no-op TracerProvider in place --
        # trace.get_current_span() then returns an invalid span at ~zero cost.

        tracer = trace.get_tracer("pinsheet.api_v1")

        @app.before_request
        def _otel_start_span():
            from flask import g, request

            if not request.path.startswith("/api/v1"):
                return
            try:
                span_cm = tracer.start_as_current_span(f"{request.method} {request.path}")
                g._otel_span_cm = span_cm
                span_cm.__enter__()
            except Exception:
                _log.debug("observability: failed to start span", exc_info=True)

        @app.teardown_request
        def _otel_end_span(_exc):
            from flask import g

            span_cm = getattr(g, "_otel_span_cm", None)
            if span_cm is not None:
                try:
                    span_cm.__exit__(None, None, None)
                except Exception:
                    _log.debug("observability: failed to end span", exc_info=True)
    except Exception:
        _log.warning("observability: init_tracing failed -- continuing without tracing", exc_info=True)


def current_trace_id() -> str:
    """Return the current span's 32-hex trace id, or a `uuid4().hex` fallback
    when OTel is disabled / no valid span context exists. ALWAYS returns a
    non-empty string and NEVER raises -- Problem Details' `traceId` field
    (ADR-002) must always be present regardless of the OTel toggle."""
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        ctx = span.get_span_context()
        if ctx is not None and ctx.is_valid:
            return trace.format_trace_id(ctx.trace_id)
    except Exception:
        _log.debug("observability: current_trace_id failed, using uuid4 fallback", exc_info=True)
    return uuid.uuid4().hex
