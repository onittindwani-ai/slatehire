import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import check_docs  # noqa: E402
import check_env  # noqa: E402
import scan_secrets  # noqa: E402

EXAMPLE = (ROOT / ".env.example").read_text()


def filled(**changes: str) -> str:
    """The example with a real session secret and the given values changed."""
    values = {"SESSION_SECRET": "test-only-" + "k3Jd8sLw0PqZx7Vn2Bm5Tc9Rf4Hy1Ga6", "DEMO_MODE": "false", "POSTGRES_PASSWORD": "abc123", **changes}
    out = []
    for line in EXAMPLE.splitlines():
        name = line.split("=", 1)[0]
        out.append(f"{name}={values[name]}" if name in values and "=" in line and not line.startswith("#") else line)
    return "\n".join(out)


def test_the_example_with_a_real_secret_is_fine():
    assert check_env.check(EXAMPLE, filled()) == []


def test_a_comment_directly_above_a_variable_does_not_start_a_group():
    groups = {g for g, n, _ in check_env.parse_example(EXAMPLE) if n == "MAX_BODY_BYTES"}
    assert len(groups) == 1 and next(iter(groups)).startswith("Core")


def test_changing_limits_or_identity_is_not_flagged_as_a_half_filled_group():
    env = filled(COMPANY_NAME="Rivera Works", LLM_CALL_BUDGET="500", LLM_BUDGET_USD="20", OWNER_EMAIL="sam@rivera.example.test", OPEN_RETENTION_DAYS="365")
    assert check_env.check(EXAMPLE, env) == []


def test_a_half_filled_adapter_group_is_still_flagged():
    problems = check_env.check(EXAMPLE, filled(WORKABLE_SUBDOMAIN="rivera"))
    assert any("WORKABLE_TOKEN" in p for p in problems)


def test_a_real_key_on_a_line_that_says_example_is_still_reported():
    key = "sk-ant-" + "a1B2c3D4e5F6g7H8i9J0k1L2"
    assert scan_secrets.scan_line(f"# example of a real key: {key}") == ["Anthropic key"]


def test_a_stub_marker_inside_the_value_is_allowed():
    assert scan_secrets.scan_line('secret = "test-only-' + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6" + '"') == []


def test_a_guide_number_with_no_guide_is_reported(tmp_path, monkeypatch, capsys):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "07-X.md").write_text("see `07` and `12`\n")
    monkeypatch.setattr(check_docs, "ROOT", tmp_path)
    monkeypatch.setattr(check_docs, "FILES", [tmp_path / "docs" / "07-X.md"])
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "counts.json").write_text("{}")
    assert check_docs.main([]) == 1
    assert "guide `12`" in capsys.readouterr().out
