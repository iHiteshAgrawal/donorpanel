from strands.session.file_session_manager import FileSessionManager
from strands.session.s3_session_manager import S3SessionManager
from strands.session.session_manager import SessionManager

from ..config import config
from .local import FileStore
from .objects import ObjectStore, ensure_bucket
from .repository import PanelRepository

__all__ = [
    "FileStore",
    "ObjectStore",
    "PanelRepository",
    "ensure_bucket",
    "session_manager",
    "store",
]


def store(prefix: str = ""):
    """Prefix scopes one actor's sandbox. Empty means the shared root, which is
    where the seed template and the global geocode cache live."""
    if config.bucket:
        return ObjectStore(prefix=prefix)
    return FileStore(config.local_root, prefix=prefix)


def session_manager(session_id: str) -> SessionManager:
    if config.bucket:
        return S3SessionManager(session_id=session_id, bucket=config.bucket,
                                prefix="sessions/", region_name=config.aws_region)
    return FileSessionManager(session_id=session_id,
                              storage_dir=f"{config.local_root}/sessions")
