from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from core.models import GridRow, Order


@dataclass(frozen=True)
class RepositoryMetadata:
    version: int | str | None = None
    revision: str | None = None


@dataclass(frozen=True)
class GridSnapshot:
    symbol: str
    rows: tuple[GridRow, ...]
    metadata: RepositoryMetadata = field(default_factory=RepositoryMetadata)


@dataclass(frozen=True)
class PendingOrdersSnapshot:
    orders: tuple[Order, ...]
    metadata: RepositoryMetadata = field(default_factory=RepositoryMetadata)


class GridStateRepository(ABC):

    @abstractmethod
    def load(self) -> GridSnapshot:
        raise NotImplementedError

    @abstractmethod
    def save(self, snapshot: GridSnapshot) -> GridSnapshot:
        raise NotImplementedError

    @abstractmethod
    def has_changed(self, metadata: RepositoryMetadata | None) -> bool:
        raise NotImplementedError


class PendingOrderRepository(ABC):

    @abstractmethod
    def add(self, order: Order) -> None:
        raise NotImplementedError

    @abstractmethod
    def get(self, order_id: str) -> Order | None:
        raise NotImplementedError

    @abstractmethod
    def remove(self, order_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def mark_filled(self, order_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def mark_cancelled(self, order_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def list_open(self) -> list[Order]:
        raise NotImplementedError
