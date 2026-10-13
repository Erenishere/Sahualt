from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


class DocumentContractError(ValueError):
    """Invalid canonical semantic input; abort the batch without fallback content."""


@dataclass(frozen=True, slots=True)
class CanonicalProductProjection:
    product_id: UUID
    name: str
    description: str
    colors: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.product_id, UUID) or self.product_id.int == 0:
            raise DocumentContractError("product_id must be a non-nil UUID")
        if not isinstance(self.name, str) or not isinstance(self.description, str):
            raise DocumentContractError("name and description must be strings")
        if not isinstance(self.colors, tuple) or any(
            not isinstance(color, str) for color in self.colors
        ):
            raise DocumentContractError("colors must be an immutable tuple of strings")
