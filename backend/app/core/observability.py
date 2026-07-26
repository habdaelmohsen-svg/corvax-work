from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.responses import Response

from app.core.config import settings

HTTP_REQUESTS = Counter(
    "corvax_http_requests_total",
    "HTTP requests processed by CORVAX",
    ["method", "route", "status"],
)
HTTP_LATENCY = Histogram(
    "corvax_http_request_duration_seconds",
    "HTTP request latency",
    ["method", "route"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30),
)
SECURITY_EVENTS = Counter(
    "corvax_security_events_total",
    "Security-relevant middleware events",
    ["event"],
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in ("request_id", "method", "path", "status", "elapsed_ms", "client_ip", "user_id", "company_id"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_logging() -> None:
    root = logging.getLogger()
    root.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    if root.handlers:
        for handler in root.handlers:
            handler.setFormatter(JsonFormatter() if settings.json_logging else logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter() if settings.json_logging else logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root.addHandler(handler)


def initialize_external_observability(app) -> None:
    if settings.sentry_dsn:
        try:
            import sentry_sdk
            from sentry_sdk.integrations.asgi import SentryAsgiMiddleware

            sentry_sdk.init(dsn=settings.sentry_dsn, environment=settings.environment, release=settings.app_version, traces_sample_rate=0.1)
            app.add_middleware(SentryAsgiMiddleware)
        except ImportError:
            logging.getLogger(__name__).warning("SENTRY_DSN configured but sentry-sdk is not installed")
    if settings.otel_exporter_otlp_endpoint:
        try:
            from opentelemetry import trace
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor

            provider = TracerProvider(resource=Resource.create({"service.name": "corvax-api", "service.version": settings.app_version}))
            provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint)))
            trace.set_tracer_provider(provider)
            FastAPIInstrumentor.instrument_app(app)
        except ImportError:
            logging.getLogger(__name__).warning("OTEL endpoint configured but OpenTelemetry SDK/instrumentation packages are not installed")


def metrics_response() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
