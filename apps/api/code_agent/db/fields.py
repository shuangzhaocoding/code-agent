from __future__ import annotations

from typing import Any

from tortoise.exceptions import FieldError
from tortoise.fields import JSONField
from tortoise.models import Model


class ScalarJSONField(JSONField):
    """JSONField that round-trips Python scalars, including str.

    Upstream Tortoise treats a Python ``str`` as already-encoded JSON text, so
    values like ``"dark"`` or ``""`` fail on save. Settings store mixed scalars,
    so encode/decode every value uniformly.
    """

    def to_db_value(self, value: Any, instance: type[Model] | Model) -> str | None:
        self.validate(value)
        if value is None:
            return None
        encoded = self.encoder(value)
        return encoded.decode() if isinstance(encoded, (bytes, bytearray)) else encoded

    def to_python_value(self, value: Any) -> Any:
        if value is None or isinstance(value, (dict, list, int, float, bool)):
            return value
        if isinstance(value, (str, bytes, bytearray)):
            try:
                return self.decoder(value)
            except Exception:
                # Bare Python str assigned before persistence (not JSON text).
                if isinstance(value, str):
                    return value
                raise FieldError(
                    f"Value {value.decode() if isinstance(value, (bytes, bytearray)) else value} is invalid json value."
                )
        return value
