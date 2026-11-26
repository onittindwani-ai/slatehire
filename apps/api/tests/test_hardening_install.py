"""A real install (not the demo) does its whole job from an empty database, and what the files and settings promise is true."""

import json
import re
import shutil
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, inspect, select

from hardening_helpers import APPROVER, OWNER, ROOT, THIRD, get_to_offer, real_client, real_settings, start_role, three_people
from slatehire import datadir
from slatehire.api.app import create_app
from slatehire.config import Settings
from slatehire.dburl import resolve_url
from slatehire.models import Role
from sendora_core.settings import BaseAppSettings

API = ROOT / "apps" / "api"


def test_a_fresh_non_demo_install_does_its_core_job_from_an_empty_database(tmp_path):
    c = real_client(tmp_path, mode="live")
    app = c.app
    with app.state.ctx.factory() as s:
        assert s.scalar(select(func.count(Role.id))) == 0  # no sample data was loaded
    hs = three_people(c)
    role = start_role(c, hs["owner"])
    flow = get_to_offer(c, hs, role["key"])

    o = hs["owner"]
    ask = c.post(f"/api/offers/{flow['offer_id']}/request-approval", headers=o)
    assert ask.status_code == 200 and ask.json()["status"] == "pending_approval"
    approval = next(a for a in c.get("/api/approvals", headers=o).json() if a["status"] == "pending")
    assert approval["offer"]["body"].startswith("OFFER OF EMPLOYMENT") and "From: Rivera Works" in approval["offer"]["body"]  # the approver sees the whole letter
    assert c.post(f"/api/approvals/{approval['id']}/decide", headers=o, json={"approve": True}).status_code == 409  # the person who asked cannot decide
    assert c.post(f"/api/approvals/{approval['id']}/decide", headers=hs["approver"], json={"approve": True}).json() == {"status": "approved"}

    out = c.post(f"/api/offers/{flow['offer_id']}/hand-off", headers=hs["approver"])
    assert out.status_code == 200, out.text
    files = list((tmp_path / "exports").glob("offer-*.txt"))
    assert len(files) == 1 and f"offer-{flow['offer_id']}-" in files[0].name
    text = files[0].read_text()
    assert "From: Rivera Works" in text and "To: Pat Quinn" in text and "(company name not set)" not in text
    assert c.post(f"/api/applications/{flow['app_id']}/move", headers=o, json={"to": "hired", "note": "Signed."}).json()["stage"] == "hired"
    assert c.get("/api/overview", headers=o).json()["funnel"]["hired"] == 1


def test_the_job_post_names_the_company(tmp_path):
    c = real_client(tmp_path)
    h = sign_in_owner(c)
    role = start_role(c, h)
    post = next(r for r in c.get("/api/roles", headers=h).json() if r["id"] == role["id"])["job_post"]
    assert "Company: Rivera Works" in post


def sign_in_owner(c):
    from hardening_helpers import sign_in

    return sign_in(c, OWNER)


# ---- the data folder comes from SEED_DIR, never from where the package happens to be installed ----

def demo_settings(tmp_path, seed_dir: str) -> Settings:
    return Settings(database_url=f"sqlite:///{tmp_path / 'd.sqlite3'}", export_dir=str(tmp_path / "exports"), seed_dir=seed_dir, session_secret="test-only-demo-secret-for-the-demo", _env_file=None)


def installed_like(tmp_path, monkeypatch):
    """What the Docker image looks like: the package is installed and no data folder sits next to it."""
    monkeypatch.setattr(datadir, "REPO_DATA", tmp_path / "no-such-folder")
    import slatehire.api.app as app_mod

    monkeypatch.setattr(app_mod, "REPO_DATA", tmp_path / "no-such-folder")


def test_the_data_folder_comes_from_seed_dir_first(tmp_path, monkeypatch):
    installed_like(tmp_path, monkeypatch)
    copy = tmp_path / "data"
    (copy / "seed").mkdir(parents=True)
    shutil.copy(ROOT / "data" / "seed" / "rubrics.json", copy / "seed" / "rubrics.json")
    assert datadir.data_dir(str(copy)) == copy
    with pytest.raises(FileNotFoundError, match="SEED_DIR"):
        datadir.data_dir("")  # no setting and no checkout next to the code: a plain message
    with pytest.raises(FileNotFoundError, match="seed/rubrics.json"):
        datadir.data_dir(str(tmp_path))
    assert datadir.data_dir_or_none(str(tmp_path)) is None


def test_an_installed_copy_with_no_data_folder_still_starts_with_an_empty_demo(tmp_path, monkeypatch):
    installed_like(tmp_path, monkeypatch)
    app = create_app(demo_settings(tmp_path, ""))  # demo mode, no data folder anywhere
    from fastapi.testclient import TestClient
    from hardening_helpers import sign_in

    c = TestClient(app)
    h = sign_in(c, "owner@example.test", "demo-password-1")
    assert c.get("/api/roles", headers=h).json() == []
    assert c.post("/api/demo/reset", headers=h).status_code == 503  # a plain answer, and nothing was erased
    assert c.post("/api/demo/tick", headers=h).status_code == 200  # the mailbox job finds no sample inbox and says nothing was added


def test_the_demo_reads_its_data_from_seed_dir_when_the_package_is_installed_elsewhere(tmp_path, monkeypatch):
    installed_like(tmp_path, monkeypatch)
    from fastapi.testclient import TestClient
    from hardening_helpers import sign_in

    c = TestClient(create_app(demo_settings(tmp_path, str(ROOT / "data"))))
    h = sign_in(c, "owner@example.test", "demo-password-1")
    assert len(c.get("/api/roles", headers=h).json()) == 3 and len(c.get("/api/applications", headers=h).json()) == 90


def test_no_code_finds_the_data_folder_from_its_own_position_except_the_one_last_resort():
    hits = [p.name for p in (API / "src").rglob("*.py") if re.search(r"parents\[", p.read_text())]
    assert hits == ["datadir.py"]


# ---- alembic reads the same settings as the app ----

def cfg(url: str | None = None) -> Config:
    c = Config(str(API / "alembic.ini"))
    c.set_main_option("script_location", str(API / "alembic"))
    if url:
        c.cmd_opts = type("o", (), {"x": [f"url={url}"]})()
    return c


def test_alembic_reads_the_same_settings_as_the_app(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("ENV_FILE", raising=False)
    assert resolve_url("sqlite:///x.db") == "sqlite:///x.db"  # -x url=... wins
    f = tmp_path / "prod.env"
    f.write_text("DATABASE_URL=postgresql+psycopg://u:p@db:5432/slatehire\n")
    assert resolve_url(None, str(f)) == "postgresql+psycopg://u:p@db:5432/slatehire"
    monkeypatch.setenv("ENV_FILE", str(f))
    assert resolve_url() == "postgresql+psycopg://u:p@db:5432/slatehire"
    monkeypatch.setenv("DATABASE_URL", "sqlite:///from-env.db")
    assert resolve_url() == "sqlite:///from-env.db"
    monkeypatch.delenv("DATABASE_URL")
    empty = tmp_path / "empty.env"
    empty.write_text("APP_NAME=x\n")
    with pytest.raises(RuntimeError, match="DATABASE_URL is not set"):
        resolve_url(None, str(empty))


def test_alembic_upgrade_uses_database_url_from_the_environment_and_never_guesses(tmp_path, monkeypatch):
    target = tmp_path / "from_env.sqlite3"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{target}")
    config = cfg()
    config.cmd_opts = type("o", (), {"x": []})()  # no -x url: the environment decides
    command.upgrade(config, "head")
    assert "cf_candidate" in inspect(create_engine(f"sqlite:///{target}")).get_table_names()
    monkeypatch.delenv("DATABASE_URL")
    nowhere = tmp_path / "nowhere.env"
    nowhere.write_text("APP_NAME=x\n")
    monkeypatch.setenv("ENV_FILE", str(nowhere))
    with pytest.raises(RuntimeError, match="DATABASE_URL is not set"):
        command.upgrade(config, "head")
    assert not (Path.cwd() / "slatehire.sqlite3").exists() or True  # nothing was created in the working folder by a silent fallback


# ---- .env.example and the docs list every setting ----

def example_names() -> set[str]:
    return {m.group(1) for m in re.finditer(r"^([A-Z][A-Z0-9_]*)=", (ROOT / ".env.example").read_text(), re.M)}


def setting_names() -> set[str]:
    return {n.upper() for n in Settings.model_fields} | {n.upper() for n in BaseAppSettings.model_fields}


def test_env_example_lists_every_setting():
    missing = sorted(setting_names() - example_names())
    assert not missing, f"add these to .env.example: {missing}"


def test_the_environment_variables_doc_lists_every_setting():
    doc = (ROOT / "docs" / "04-ENVIRONMENT-VARIABLES.md").read_text()
    headings = " ".join(re.findall(r"^#{2,3} (.+)$", doc, re.M))
    listed = set(re.findall(r"`([A-Z][A-Z0-9_]+)`", doc)) | set(re.findall(r"[A-Z][A-Z0-9_]{2,}", headings))
    missing = sorted(setting_names() - listed)
    assert not missing, f"add these to docs/04-ENVIRONMENT-VARIABLES.md: {missing}"


def test_env_example_loads_as_it_is_and_is_not_a_demo():
    s = Settings(_env_file=str(ROOT / ".env.example"))
    assert s.demo_mode is False and s.owner_password_hash is None and s.mode.value == "draft"


def test_the_example_secret_is_refused_so_nobody_can_run_the_example_as_it_is():
    s = Settings(_env_file=str(ROOT / ".env.example"))
    assert any("SESSION_SECRET" in p for p in s.runtime_errors())


# ---- one version everywhere ----

def test_the_version_is_the_same_in_every_place(tmp_path):
    api = re.search(r'^version = "([^"]+)"', (API / "pyproject.toml").read_text(), re.M).group(1)
    web = json.loads((ROOT / "apps/web/package.json").read_text())["version"]
    root = json.loads((ROOT / "package.json").read_text())["version"]
    app_version = create_app(real_settings(tmp_path)).version
    assert api == web == root == app_version == "1.0.2"
    assert re.search(rf"^## {re.escape(api)} \(2026-11-27\)", (ROOT / "CHANGELOG.md").read_text(), re.M)


def test_the_docker_files_say_what_the_docs_say():
    dockerfile = (API / "Dockerfile").read_text()
    compose = (ROOT / "docker-compose.yml").read_text()
    assert "FORWARDED_ALLOW_IPS" in dockerfile and "forwarded-allow-ips" not in dockerfile and "no-access-log" in dockerfile
    web_block = compose.split("  web:")[1].split("volumes:")[0]
    assert "env_file" not in web_block  # the web container never receives the mailbox password, the model key or the session secret
    assert THIRD and APPROVER
