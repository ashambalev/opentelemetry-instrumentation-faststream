import pytest
from faststream.redis import RedisBroker
from opentelemetry.instrumentation.faststream import FastStreamInstrumentator


@pytest.mark.asyncio
async def test_instrumentation():
    FastStreamInstrumentator().instrument()
    broker = RedisBroker("redis://localhost:6379")
    assert len(broker._middlewares) == 1
    assert broker._middlewares[0].__name__ == "RedisOtelMiddleware"  # type: ignore

    FastStreamInstrumentator().uninstrument()
    assert len(broker._middlewares) == 0
