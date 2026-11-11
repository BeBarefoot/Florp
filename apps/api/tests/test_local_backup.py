import hashlib
import json
from pathlib import Path
import sqlite3
import zipfile

import pytest
from sqlmodel import SQLModel, Session, create_engine
from app.local_backup import create, restore
from app.local_lock import workspace_lock
from app.models import Project, Blueprint, PlanRevision, SceneRevision, SceneRenderJob


@pytest.fixture
def workspace(tmp_path):
    database = tmp_path / 'florp.db'
    storage = tmp_path / 'storage'
    storage.mkdir()
    engine = create_engine(f'sqlite:///{database}')
    SQLModel.metadata.create_all(engine)
    folder = storage / 'bp'
    folder.mkdir()
    original = folder / 'original.bin'
    preview = folder / 'preview.png'
    original.write_bytes(b'synthetic original')
    preview.write_bytes(b'synthetic preview')
    capture = folder / 'scene-renders' / 'job'
    capture.mkdir(parents=True)
    (capture / 'result.png').write_bytes(b'synthetic result')
    with Session(engine) as session:
        session.add(Project(id='project', title='Home'))
        session.add(Blueprint(id='bp', project_id='project', filename='plan.png', local_path=str(original), preview_path=str(preview), width=80, height=40))
        session.add(PlanRevision(blueprint_id='bp', revision=1, model={'test':'geometry'}))
        session.add(SceneRevision(blueprint_id='bp', revision=1, plan_revision=1, config={'views':['camera']}))
        session.add(SceneRenderJob(id='job', blueprint_id='bp', request_key='one', input_hash='hash', scene_revision=1, plan_revision=1, view_id='camera', name='Image', prompt='Style', provider_model='mock', status='complete'))
        session.commit()
    engine.dispose()
    return database, storage


def test_full_workspace_restore_preserves_revisions_assets_and_rebases_paths(workspace, tmp_path):
    database, storage = workspace
    before = database.read_bytes()
    archive = create(database, storage, tmp_path / 'backup.zip')
    result = restore(archive, tmp_path / 'restored')
    assert database.read_bytes() == before
    with sqlite3.connect(result / 'florp.db') as db:
        assert db.execute('SELECT title FROM project').fetchone()[0] == 'Home'
        assert db.execute('SELECT revision FROM planrevision').fetchone()[0] == 1
        assert json.loads(db.execute('SELECT config FROM scenerevision').fetchone()[0]) == {'views':['camera']}
        assert db.execute('SELECT status FROM scenerenderjob').fetchone()[0] == 'complete'
        original, preview = db.execute('SELECT local_path, preview_path FROM blueprint').fetchone()
        assert Path(original).is_relative_to(result)
        assert Path(preview).read_bytes() == b'synthetic preview'
    assert (result / 'storage/bp/scene-renders/job/result.png').read_bytes() == b'synthetic result'
    with pytest.raises(ValueError, match='already exists'):
        create(database, storage, archive)
    with pytest.raises(ValueError, match='new directory'):
        restore(archive, result)


def test_backup_cannot_race_running_api(workspace, tmp_path):
    database, storage = workspace
    with workspace_lock(database):
        with pytest.raises(RuntimeError, match='Stop the API'):
            create(database, storage, tmp_path / 'backup.zip')
    assert not (tmp_path / 'backup.zip').exists()
    create(database, storage, tmp_path / 'backup.zip')


@pytest.mark.parametrize('attack', ['checksum', 'traversal', 'missing'])
def test_invalid_backup_never_creates_restore_destination(workspace, tmp_path, attack):
    archive = create(*workspace, tmp_path / 'good.zip')
    with zipfile.ZipFile(archive) as source:
        entries = {name:source.read(name) for name in source.namelist()}
    manifest = json.loads(entries['manifest.json'])
    if attack == 'checksum':
        entries['storage/bp/preview.png'] = b'tampered'
    elif attack == 'traversal':
        key = 'storage/../../escaped'
        entries[key] = b'bad'
        manifest['files'][key] = {'size':3, 'sha256':hashlib.sha256(b'bad').hexdigest()}
    else:
        del entries['storage/bp/preview.png']
    entries['manifest.json'] = json.dumps(manifest).encode()
    bad = tmp_path / 'bad.zip'
    with zipfile.ZipFile(bad, 'w') as output:
        for name, content in entries.items():
            output.writestr(name, content)
    with pytest.raises(ValueError):
        restore(bad, tmp_path / 'recovered')
    assert not (tmp_path / 'recovered').exists()
    assert not (tmp_path / 'escaped').exists()


def test_missing_referenced_source_fails_backup(workspace, tmp_path):
    (workspace[1] / 'bp/preview.png').unlink()
    with pytest.raises(ValueError, match='missing'):
        create(*workspace, tmp_path / 'backup.zip')
    assert not (tmp_path / 'backup.zip').exists()
