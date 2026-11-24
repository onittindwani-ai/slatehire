import pytest

from sendora_core.db import create_all, make_engine, make_session_factory, session_scope
from sendora_core.settings import BaseAppSettings, Mode


@pytest.fixture
def settings(tmp_path):
    return BaseAppSettings(database_url=f"sqlite:///{tmp_path}/t.sqlite3", _env_file=None)


@pytest.fixture
def live_settings(tmp_path):
    return BaseAppSettings(database_url=f"sqlite:///{tmp_path}/t.sqlite3", mode=Mode.LIVE, demo_mode=False, _env_file=None)


@pytest.fixture
def factory(settings):
    engine = make_engine(settings.database_url)
    create_all(engine)
    return make_session_factory(engine)


@pytest.fixture
def session(factory):
    with session_scope(factory) as s:
        yield s
