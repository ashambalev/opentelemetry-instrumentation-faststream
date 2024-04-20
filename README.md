# FastStream instrumentation for OpenTelemetry

[![PyPI - Version](https://img.shields.io/pypi/v/opentelemetry-instrumentation-faststream.svg)](https://pypi.org/project/opentelemetry-instrumentation-faststream)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/opentelemetry-instrumentation-faststream.svg)](https://pypi.org/project/opentelemetry-instrumentation-faststream)


This library allows tracing requests made by the [**FastStream**](https://faststream.airt.ai/latest/) library.


## Installation

```console
pip install opentelemetry-instrumentation-faststream
```

## Usage

### Middlewares

#### Redis

```python
from opentelemetry.instrumentation.faststream.middlewares import RedisOtelMiddleware

broker = RedisBroker("redis://localhost:6379", middlewares=[RedisOtelMiddleware])
```

#### Kafka

```python
from opentelemetry.instrumentation.faststream.middlewares import KafkaOtelMiddleware

broker = KafkaBroker("redis://localhost:6379", middlewares=[KafkaOtelMiddleware])
```

#### RabbitMQ

```python
from opentelemetry.instrumentation.faststream.middlewares import RabbitOtelMiddleware

broker = RabbitBroker("redis://localhost:6379", middlewares=[RabbitOtelMiddleware])
```

#### NATS

```python
from opentelemetry.instrumentation.faststream.middlewares import NatsOtelMiddleware

broker = NatsBroker("redis://localhost:6379", middlewares=[NatsOtelMiddleware])
```

### Instrumentation

```python
from opentelemetry.instrumentation.faststream import FastStreamInstrumentator

# Instrument all brokers automatically
FastStreamInstrumentator().instrument()

# Uninstrument
FastStreamInstrumentator().uninstrument()
```

## License

`opentelemetry-instrumentation-faststream` is distributed under the terms of the [MIT](https://spdx.org/licenses/MIT.html) license.
