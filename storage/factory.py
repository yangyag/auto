from storage.file_grid_repository import FileGridRepository, FilePendingOrderRepository
from storage.interfaces import GridStateRepository, PendingOrderRepository


FILE_BACKEND = "file"
POSTGRES_BACKEND = "postgres"


def _get_backend(config) -> str:
    backend = getattr(config, "STATE_BACKEND", FILE_BACKEND)
    return str(backend).strip().lower() or FILE_BACKEND


def build_grid_repository(config, *, grid_file: str | None = None) -> GridStateRepository:
    backend = _get_backend(config)
    if backend == FILE_BACKEND:
        return FileGridRepository(grid_file or getattr(config, "GRID_FILE", "grid.txt"))
    if backend == POSTGRES_BACKEND:
        from storage.postgres_grid_repository import PostgresGridRepository

        return PostgresGridRepository.from_config(config)
    raise ValueError(f"지원하지 않는 상태 저장 백엔드: {backend}")


def build_pending_order_repository(config) -> PendingOrderRepository:
    backend = _get_backend(config)
    if backend == FILE_BACKEND:
        return FilePendingOrderRepository()
    if backend == POSTGRES_BACKEND:
        from storage.postgres_order_repository import PostgresOrderRepository

        return PostgresOrderRepository.from_config(config)
    raise ValueError(f"지원하지 않는 상태 저장 백엔드: {backend}")
