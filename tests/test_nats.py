import pytest
from faststream import Context
from faststream.nats import NatsBroker, TestNatsBroker
from opentelemetry import trace
from opentelemetry.instrumentation.faststream.middlewares import NatsOtelMiddleware
from opentelemetry.sdk.trace import TracerProvider

broker = NatsBroker("nats://localhost:4222", middlewares=[NatsOtelMiddleware])
provider = TracerProvider()
trace.set_tracer_provider(provider)
tracer = trace.get_tracer(__name__)


@broker.subscriber("test-channel")
async def handle(msg, span=Context("span")):
    return span.get_span_context().trace_id


@pytest.mark.asyncio
async def test_nats_broker():
    with tracer.start_as_current_span("test-span") as span:
        async with TestNatsBroker(broker) as br:
            trace_id = span.get_span_context().trace_id
            inner_trace_id = await br.publish(trace_id, subject="test-channel", rpc=True)
            assert inner_trace_id == trace_id

    assert handle.mock is None
