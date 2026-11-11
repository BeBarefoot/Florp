"""One active local API or backup operation per SQLite workspace (macOS/Linux)."""
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def workspace_lock(database):
    import fcntl
    path = Path(database).resolve().with_suffix('.florp.lock')
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError('Florp is using this workspace. Stop the API before backing up, or close the other API instance.') from exc
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)
