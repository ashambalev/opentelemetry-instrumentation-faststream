import pytest
from faststream import Context
from faststream.redis import RedisBroker, TestRedisBroker
from opentelemetry import trace
from opentelemetry.instrumentation.faststream.middlewares import RedisOtelMiddleware
from opentelemetry.sdk.trace import TracerProvider

broker = RedisBroker("redis://localhost:6379", middlewares=[RedisOtelMiddleware])
provider = TracerProvider()
trace.set_tracer_provider(provider)
tracer = trace.get_tracer(__name__)


@broker.subscriber("test-channel")
async def handle(msg, span=Context("span")):
    return span.get_span_context().trace_id


@pytest.mark.asyncio
async def test_redis_broker():
    with tracer.start_as_current_span("test-span") as span:
        async with TestRedisBroker(broker) as br:
            trace_id = span.get_span_context().trace_id
            inner_trace_id = await br.publish(trace_id, channel="test-channel", rpc=True)
            assert inner_trace_id == trace_id

    assert handle.mock is None
