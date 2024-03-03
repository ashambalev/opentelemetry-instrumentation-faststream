from functools import wraps
from timeit import default_timer
from typing import Any, Collection

import wrapt
from opentelemetry import metrics, propagate, trace
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import MetricReader
from opentelemetry.sdk.resources import SERVICE_NAME, SERVICE_VERSION, Resource
from opentelemetry.sdk.trace import TracerProvider, SpanProcessor
from opentelemetry.semconv.trace import SpanAttributes

from faststream import FastStream
from faststream.broker.message import StreamMessage
from faststream.utils import context as faststream_context
from faststream_instrumentation.package import _instruments
from faststream_instrumentation.version import __version__

tracer = trace.get_tracer(__name__)
meter = metrics.get_meter(__name__, __version__)

_DEFAULT_ATTRIBUTES = {
    SpanAttributes.MESSAGING_SYSTEM: "redis",
}

_ATTRIBUTE_MESSAGE_MAPPING = {
    SpanAttributes.MESSAGING_MESSAGE_ID: "message_id",
    SpanAttributes.MESSAGING_CONVERSATION_ID: "correlation_id",
}


def _attributes_from_message(
    msg: StreamMessage[Any] | dict[str, Any], attr_type: list[str] | None = None
) -> dict[str, Any]:
    attributes = _DEFAULT_ATTRIBUTES.copy()
    if attr_type is None:
        attr_type = list(_ATTRIBUTE_MESSAGE_MAPPING.keys())
    for attr in attr_type:
        if attr not in  _ATTRIBUTE_MESSAGE_MAPPING.keys():
            continue
        if isinstance(msg, dict):
            val = msg.get(_ATTRIBUTE_MESSAGE_MAPPING[attr], None)
            if val:
                attributes[attr] = val
        else:
            val = getattr(msg, _ATTRIBUTE_MESSAGE_MAPPING[attr], None)
            if val:
                attributes[attr] = val
    return attributes


_duration_attrs :list[str]= [
    SpanAttributes.MESSAGING_SYSTEM,
    SpanAttributes.MESSAGING_DESTINATION,
    SpanAttributes.MESSAGING_MESSAGE_ID,
    SpanAttributes.MESSAGING_CONVERSATION_ID,
]

_requests_attrs: list[str] = [
    SpanAttributes.MESSAGING_SYSTEM,
    SpanAttributes.MESSAGING_DESTINATION,
    SpanAttributes.MESSAGING_MESSAGE_ID,
    SpanAttributes.MESSAGING_CONVERSATION_ID,
]


class FastStreamInstrumentator(BaseInstrumentor):
    @staticmethod
    def _instrument_broker(broker_cls):
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

        def process_message_wrapper(f, instance, args, kwargs):
            wrapped_func = f(*args, **kwargs)

            @wraps(wrapped_func)
            async def process_wrapper(message: StreamMessage[Any]):
                span_context = propagate.extract(message.headers)
                requests_attrs = _attributes_from_message(message, _requests_attrs)
                duration_attrs = _attributes_from_message(message, _duration_attrs)
                start = default_timer()
                active_requests_counter.add(1, requests_attrs)
                try:
                    with tracer.start_as_current_span(
                        name=wrapped_func.__name__, context=span_context
                    ) as current_span:
                        current_span.set_attributes(requests_attrs)
                        faststream_context.set_local("span", current_span)
                        return await wrapped_func(message)
                finally:
                    duration = max(round((default_timer() - start) * 1000), 0)
                    duration_histogram.record(duration, duration_attrs)
                    active_requests_counter.add(-1, requests_attrs)

            return process_wrapper

        wrapt.wrap_function_wrapper(broker_cls, "_process_message", process_message_wrapper)

    @staticmethod
    def _instrument_producer(producer_cls):
        message_size_histogram = meter.create_histogram(
            name="faststream.message.size",
            unit="By",
            description="measures the size of published messages",
        )

        async def publish_wrapper(f, instance, args, kwargs):
            headers = kwargs.pop("headers", {})
            requests_attrs = _attributes_from_message(kwargs, _requests_attrs)
            requests_attrs[SpanAttributes.MESSAGING_DESTINATION] = kwargs.get("stream", "")

            span = trace.get_current_span()
            span.set_attributes(requests_attrs)
            propagate.inject(headers)
            message_size_histogram.record(len(kwargs.get("body", "")))
            return await f(*args, headers=headers, **kwargs)

        wrapt.wrap_function_wrapper(producer_cls, "publish", publish_wrapper)

    @staticmethod
    def instrument_redis_broker():
        from faststream.redis.broker import RedisBroker
        from faststream.redis.producer import RedisFastProducer

        FastStreamInstrumentator._instrument_broker(RedisBroker)
        FastStreamInstrumentator._instrument_producer(RedisFastProducer)

    @staticmethod
    def uninstrument_redis_broker():
        from faststream.redis.broker import RedisBroker
        from faststream.redis.producer import RedisFastProducer

        unwrap(RedisBroker, "_process_message")
        unwrap(RedisFastProducer, "publish")

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    @staticmethod
    def instrument_app(
        app: FastStream,
        resource: Resource | None = None,
        tracer_provider: TracerProvider | None = None,
        meter_provider: MeterProvider | None= None,
        span_processor: SpanProcessor | None= None,
        metric_readers: list[MetricReader] | None= None,
    ):
        if resource is None:
            resource = Resource(
                attributes={SERVICE_NAME: app.identifier or "faststream", SERVICE_VERSION: app.version}
            )
        tracer_provider = tracer_provider or TracerProvider(resource=resource)
        if span_processor:
            tracer_provider.add_span_processor(span_processor)
        trace.set_tracer_provider(tracer_provider)

        if meter_provider is None and metric_readers:
            meter_provider = MeterProvider(resource=resource, metric_readers=metric_readers)
        meter_provider = meter_provider or MeterProvider(resource=resource)

        metrics.set_meter_provider(meter_provider)

        app.tracer = tracer_provider.get_tracer(__name__, __version__) # type: ignore
        match app.broker.__class__.__name__:
            case "RedisBroker":
                FastStreamInstrumentator.instrument_redis_broker()

    @staticmethod
    def uninstrument_app(app: FastStream):
        app.tracer = None # type: ignore
        match app.broker.__class__.__name__:
            case "RedisBroker":
                FastStreamInstrumentator.uninstrument_redis_broker()