from timeit import default_timer
from typing import Any, Awaitable, Callable

from opentelemetry import metrics, propagate, trace
from opentelemetry.instrumentation.faststream.version import __version__
from opentelemetry.semconv.trace import SpanAttributes

from faststream import BaseMiddleware
from faststream.broker.message import StreamMessage
from faststream.utils import context as faststream_context

tracer = trace.get_tracer(__name__)
meter = metrics.get_meter(__name__, __version__)

duration_histogram = meter.create_histogram(
    name="faststream.consume.duration",
    unit="ms",
    description="measures the duration of message consumption",
)
active_requests_counter = meter.create_up_down_counter(
    name="faststream.active_requests",
    unit="requests",
    description="measures the number of concurrent messages that are currently in-flight",
)
message_size_histogram = meter.create_histogram(
    name="faststream.message.size",
    unit="By",
    description="measures the size of published messages",
)


class BaseOtelMiddleware(BaseMiddleware):
    def _attributes_from_message(self, msg: StreamMessage[Any]) -> dict[str, Any]:
        return {
            SpanAttributes.MESSAGING_MESSAGE_ID: msg.message_id,
            SpanAttributes.MESSAGING_CONVERSATION_ID: msg.correlation_id,
        }

    def _get_destination_name(self, options: dict[str, Any]) -> str: ...

    def _get_system(self) -> str: ...

    def _attributes_from_publish_options(self, options: dict[str, Any]) -> dict[str, Any]:
        return {
            SpanAttributes.MESSAGING_SYSTEM: self._get_system(),
            SpanAttributes.MESSAGING_DESTINATION_NAME: self._get_destination_name(options),
            SpanAttributes.MESSAGING_MESSAGE_ID: options.get("message_id", ""),
            SpanAttributes.MESSAGING_CONVERSATION_ID: options.get("correlation_id", ""),
        }

    async def consume_scope(
        self,
        call_next: Callable[[Any], Awaitable[Any]],
        msg: StreamMessage[Any],
    ) -> Any:
        span_context = propagate.extract(msg.headers)
        attrs = self._attributes_from_message(msg)
        start = default_timer()
        active_requests_counter.add(1, attrs)
        try:
            with tracer.start_as_current_span(
                name=call_next.__self__._wrapped_call.__name__, context=span_context
            ) as current_span:
                current_span.set_attributes(attrs)
                faststream_context.set_local("span", current_span)
                return await call_next(msg)
        finally:
            duration = max(round((default_timer() - start) * 1000), 0)
            duration_histogram.record(duration, attrs)
            active_requests_counter.add(-1, attrs)

    async def publish_scope(
        self,
        call_next: Callable[..., Awaitable[Any]],
        msg: Any,
        **options: Any,
    ) -> Any:
        headers = options.pop("headers") or {}
        requests_attrs = self._attributes_from_publish_options(options)
        span = trace.get_current_span()
        span.set_attributes(requests_attrs)
        propagate.inject(headers)
        message_size_histogram.record(len(options.get("body", "")))
        return await call_next(msg, headers=headers, **options)


class RedisOtelMiddleware(BaseOtelMiddleware):
    def _get_destination_name(self, options: dict[str, Any]) -> str:
        name = options.get("channel") or options.get("list") or options.get("stream")
        if name is not None and not isinstance(name, str):
            name = name.name
        return name or ""

    def _get_system(self) -> str:
        return "faststream.redis"


class NatsOtelMiddleware(BaseOtelMiddleware):
    def _get_destination_name(self, options: dict[str, Any]) -> str:
        name = options.get("routing_key")
        exchange = options.get("exchange")
        if name is not None and not isinstance(name, str):
            name = name.name
        if exchange is not None and not isinstance(exchange, str):
            exchange = exchange.name
        if exchange and name:
            name = f"{exchange}.{name}"
        return name or ""

    def _get_system(self) -> str:
        return "faststream.nats"


class KafkaOtelMiddleware(BaseOtelMiddleware):
    def _get_destination_name(self, options: dict[str, Any]) -> str:
        return options.get("topic") or ""

    def _get_system(self) -> str:
        return "faststream.kafka"


class RabbitOtelMiddleware(BaseOtelMiddleware):
    def _get_destination_name(self, options: dict[str, Any]) -> str:
        return options.get("subject") or ""

    def _get_system(self) -> str:
        return "faststream.rabbit"
