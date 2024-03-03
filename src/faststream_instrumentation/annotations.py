from opentelemetry import trace
from typing_extensions import Annotated

from faststream.utils.context import Context

TelemetrySpan = Annotated[trace.Span, Context("span", cast=True)]
