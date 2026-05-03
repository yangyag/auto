from app.storage.interfaces import GridStateRepository, PendingOrderRepository
from app.storage.postgres_grid_repository import PostgresGridRepository
from app.storage.postgres_order_repository import PostgresOrderRepository


def build_grid_repository(config) -> GridStateRepository:
    return PostgresGridRepository.from_config(config)


def build_pending_order_repository(config) -> PendingOrderRepository:
    return PostgresOrderRepository.from_config(config)
