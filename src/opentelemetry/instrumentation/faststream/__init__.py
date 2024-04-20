from typing import Callable, Collection

from opentelemetry.instrumentation.faststream.middlewares import (
    BaseOtelMiddleware,
    KafkaOtelMiddleware,
    NatsOtelMiddleware,
    RabbitOtelMiddleware,
    RedisOtelMiddleware,
)
from opentelemetry.instrumentation.faststream.package import _instruments
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import unwrap
from wrapt import wrap_function_wrapper


def _wrap_init_broker(middleware_class) -> Callable:
    def _overriden_init(func, instance, args, kwargs):
        kwargs["middlewares"] = (middleware_class,) + kwargs.pop("middlewares", ())
        FastStreamInstrumentator._instrumented_brokers.add(instance)
        instance._is_instrumented_by_opentelemetry = True
        return func(*args, **kwargs)

    return _overriden_init


class FastStreamInstrumentator(BaseInstrumentor):
    _instrumented_brokers = set()

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument_redis_broker(self):
        try:
            from faststream.redis import RedisBroker
        except ImportError:
            return

        wrap_function_wrapper(RedisBroker, "__init__", _wrap_init_broker(RedisOtelMiddleware))

    def _instrument_kafka_broker(self):
        try:
            from faststream.kafka import KafkaBroker
        except ImportError:
            return

        wrap_function_wrapper(KafkaBroker, "__init__", _wrap_init_broker(KafkaOtelMiddleware))

    def _instrument_confluent_broker(self):
        try:
            from faststream.confluent import KafkaBroker
        except ImportError:
            return

        wrap_function_wrapper(KafkaBroker, "__init__", _wrap_init_broker(KafkaOtelMiddleware))

    def _instrument_rabbit_broker(self):
        try:
            from faststream.rabbit import RabbitBroker
        except ImportError:
            return

        wrap_function_wrapper(RabbitBroker, "__init__", _wrap_init_broker(RabbitOtelMiddleware))

    def _instrument_nats_broker(self):
        try:
            from faststream.nats import NatsBroker
        except ImportError:
            return

        wrap_function_wrapper(NatsBroker, "__init__", _wrap_init_broker(NatsOtelMiddleware))

    def _instrument(self, **opts):
        self._instrument_redis_broker()
        self._instrument_kafka_broker()
        self._instrument_confluent_broker()
        self._instrument_rabbit_broker()
        self._instrument_nats_broker()

    def _uninstrument(self, **kwargs):
        for broker in FastStreamInstrumentator._instrumented_brokers:
            self._remove_instrumented_middleware(broker)
        FastStreamInstrumentator._instrumented_brokers.clear()

        try:
            from faststream.redis import RedisBroker

            unwrap(RedisBroker, "__init__")
        except (AttributeError, ImportError):
            pass
        try:
            from faststream.kafka import KafkaBroker

            unwrap(KafkaBroker, "__init__")
        except (AttributeError, ImportError):
            pass
        try:
            from faststream.confluent import KafkaBroker

            unwrap(KafkaBroker, "__init__")
        except (AttributeError, ImportError):
            pass
        try:
            from faststream.rabbit import RabbitBroker

            unwrap(RabbitBroker, "__init__")
        except (AttributeError, ImportError):
            pass
        try:
            from faststream.nats import NatsBroker

            unwrap(NatsBroker, "__init__")
        except (AttributeError, ImportError):
            pass

    def _remove_instrumented_middleware(self, broker):
        if (
            hasattr(broker, "_is_instrumented_by_opentelemetry")
            and broker._is_instrumented_by_opentelemetry
        ):
            broker._middlewares = tuple(
                middleware
                for middleware in broker._middlewares
                if not issubclass(middleware, BaseOtelMiddleware)
            )
            broker._is_instrumented_by_opentelemetry = False
