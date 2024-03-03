from faststream.utils.context import Context
from opentelemetry import trace
from typing_extensions import Annotated

TelemetrySpan = Annotated[trace.Span, Context("span", cast=True)]
