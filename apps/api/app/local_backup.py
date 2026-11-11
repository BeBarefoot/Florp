"""Offline full-workspace backup/restore for the local macOS/Linux application."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import stat
import tempfile
import zipfile
from .local_lock import workspace_lock

PREFIX = '__FLORP_STORAGE__/'
MAX_BYTES = 10 * 1024**3


def digest(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def rewrite_paths(database, convert):
    with sqlite3.connect(database) as conn:
        conn.execute('PRAGMA trusted_schema=OFF')
        if conn.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Backup database failed integrity check')
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'project', 'blueprint', 'planrevision', 'scenerevision'} <= tables:
            raise ValueError('Not a current Florp workspace database')
        for table, columns in [('blueprint', ['local_path', 'preview_path']), ('render', ['image_path'])]:
            if table not in tables:
                continue
            for column in columns:
                for row_id, value in conn.execute(f'SELECT id, {column} FROM {table}').fetchall():
                    if value:
                        conn.execute(f'UPDATE {table} SET {column}=? WHERE id=?', (convert(value), row_id))


def create(database, storage, destination):
    database, storage, destination = map(lambda p: Path(p).expanduser().resolve(), (database, storage, destination))
    if destination.exists():
        raise ValueError('Backup destination already exists; choose a new filename')
    if not database.is_file() or not storage.is_dir():
        raise ValueError('Workspace database or storage is missing')
    if destination.is_relative_to(storage):
        raise ValueError('Save backups outside the workspace storage directory')
    with workspace_lock(database), tempfile.TemporaryDirectory(dir=destination.parent) as tmp:
        stage = Path(tmp)
        copy = stage / 'florp.db'
        with sqlite3.connect(f'{database.as_uri()}?mode=ro', uri=True) as source, sqlite3.connect(copy) as target:
            source.backup(target)
        def portable(value):
            path = Path(value).resolve()
            if not path.is_relative_to(storage) or not path.is_file() or path.is_symlink():
                raise ValueError('A referenced project file is missing or outside STORAGE_PATH')
            return PREFIX + path.relative_to(storage).as_posix()
        rewrite_paths(copy, portable)
        entries = {'florp.db': copy}
        for path in sorted(storage.rglob('*')):
            if path.is_symlink():
                raise ValueError('Symlinks in workspace storage are not supported')
            if path.is_file():
                if path.name.startswith('restore-') and path.suffix == '.json':
                    raise ValueError('Finish the pending dataset restore by starting and stopping Florp before backup')
                entries['storage/' + path.relative_to(storage).as_posix()] = path
        if len(entries) > 50000 or sum(p.stat().st_size for p in entries.values()) > MAX_BYTES:
            raise ValueError('Workspace exceeds the 10 GiB / 50,000-file backup limit')
        manifest = {'format': 'florp-local-backup', 'version': 1, 'files': {}}
        archive = stage / 'backup.zip'
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as output:
            for name, path in entries.items():
                manifest['files'][name] = {'sha256': digest(path), 'size': path.stat().st_size}
                output.write(path, name)
            output.writestr('manifest.json', json.dumps(manifest, indent=2))
        # Atomic, exclusive publication: never replace an existing backup.
        os.link(archive, destination)
    return destination


def restore(archive, destination):
    archive, destination = Path(archive).expanduser().resolve(), Path(destination).expanduser().resolve()
    if destination.exists():
        raise ValueError('Restore requires a new directory; existing data is never overwritten')
    with tempfile.TemporaryDirectory(dir=destination.parent) as tmp:
        stage = Path(tmp)
        with zipfile.ZipFile(archive) as source:
            names = source.namelist()
            if len(names) != len(set(names)) or len(names) > 50001:
                raise ValueError('Duplicate or excessive backup entries')
            if sum(i.file_size for i in source.infolist()) > MAX_BYTES:
                raise ValueError('Backup exceeds the 10 GiB expanded limit')
            info = source.getinfo('manifest.json')
            if info.file_size > 16 * 1024**2:
                raise ValueError('Backup manifest is too large')
            manifest = json.loads(source.read(info))
            if manifest.get('format') != 'florp-local-backup' or manifest.get('version') != 1:
                raise ValueError('Unsupported backup format')
            files = manifest['files']
            if set(names) != {'manifest.json', *files} or 'florp.db' not in files:
                raise ValueError('Backup inventory does not match manifest')
            for name, meta in files.items():
                part = PurePosixPath(name)
                if ('\\' in name or part.is_absolute() or '..' in part.parts or
                    (name != 'florp.db' and not name.startswith('storage/'))):
                    raise ValueError('Unsafe backup path')
                item = source.getinfo(name)
                if stat.S_ISLNK(item.external_attr >> 16) or item.is_dir():
                    raise ValueError('Backup entries must be regular files')
                path = stage / name
                path.parent.mkdir(parents=True, exist_ok=True)
                with source.open(item) as src, path.open('xb') as dst:
                    shutil.copyfileobj(src, dst, 1024 * 1024)
                if path.stat().st_size != meta['size'] or digest(path) != meta['sha256']:
                    raise ValueError('Backup checksum mismatch')
        def relocated(value):
            if not value.startswith(PREFIX):
                raise ValueError('Backup contains an unportable file reference')
            relative = value[len(PREFIX):]
            path = (stage / 'storage' / relative).resolve()
            if not path.is_relative_to(stage / 'storage') or not path.is_file():
                raise ValueError('Backup is missing a referenced project file')
            return str(destination / 'storage' / path.relative_to(stage / 'storage'))
        rewrite_paths(stage / 'florp.db', relocated)
        (stage / 'storage').mkdir(exist_ok=True)
        destination.mkdir()  # exclusive; never claim or replace an existing directory
        try:
            (stage / 'florp.db').rename(destination / 'florp.db')
            (stage / 'storage').rename(destination / 'storage')
        except Exception:
            shutil.rmtree(destination)
            raise
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    backup = sub.add_parser('create', help='Stop Florp first; copies all local projects and artifacts')
    backup.add_argument('destination')
    recover = sub.add_parser('restore', help='Validate and restore into a NEW directory')
    recover.add_argument('archive')
    recover.add_argument('destination')
    args = parser.parse_args()
    try:
        if args.command == 'create':
            from sqlalchemy.engine import make_url
            from .config import settings
            url = make_url(settings.database_url)
            if url.get_backend_name() != 'sqlite' or not url.database:
                raise ValueError('Local backup requires a file-backed SQLite database')
            print(f'Backup created: {create(url.database, settings.storage_path, args.destination)}')
        else:
            restored = restore(args.archive, args.destination)
            print(f'Restored to: {restored}\nSet DATABASE_URL=sqlite:///{restored}/florp.db\nSet STORAGE_PATH={restored}/storage\nKeep provider keys in your existing .env; they are not included.')
    except (ValueError, RuntimeError, OSError, sqlite3.DatabaseError, zipfile.BadZipFile, KeyError, TypeError) as exc:
        parser.exit(1, f'{exc}\n')


if __name__ == '__main__':
    main()
