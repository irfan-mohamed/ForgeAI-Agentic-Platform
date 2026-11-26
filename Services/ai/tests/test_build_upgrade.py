"""
Unit tests for ForgeAI Build Execution Graph upgrades:
  - Strict patch application and integration-test exit handling
  - JS/TS test detection (_has_js_tests, _detect_js_test_runner)
  - Missing env var detection (_detect_missing_env_vars)
  - Test block extraction from testing_agent markdown (_extract_test_blocks)
  - Retry loop routing (_should_continue_after_tests)
"""
import os
import json
import io
import tarfile
import tempfile
from contextlib import nullcontext
from subprocess import CompletedProcess
from types import SimpleNamespace
import pytest

from app.services import build_execution_graph as build
from app.services.build_execution_graph import (
    _detect_js_test_runner,
    _detect_missing_env_vars,
    _extract_test_blocks,
    _has_js_tests,
    _should_continue_after_tests,
    MAX_PATCH_RETRIES,
)


def test_test_only_plan_generates_git_diff_and_preserves_route(tmp_path, monkeypatch):
    directory = str(tmp_path)
    assert build._git("init", cwd=directory).returncode == 0
    route = tmp_path / "chat.py"
    route.write_text("def chat():\n    return {'reply': 'ok'}\n", encoding="utf-8")
    assert build._git("add", "--", "chat.py", cwd=directory).returncode == 0
    assert build._git("-c", "user.name=Test", "-c", "user.email=test@example.com",
                      "commit", "-m", "base", cwd=directory).returncode == 0
    base = build._git("rev-parse", "HEAD", cwd=directory).stdout.decode().strip()
    row = SimpleNamespace(generated_patches=None)
    db = SimpleNamespace(query=lambda *_: SimpleNamespace(filter=lambda *_: SimpleNamespace(first=lambda: row)))
    monkeypatch.setattr(build, "db_session", lambda: nullcontext(db))
    monkeypatch.setattr(build, "_log", lambda *_: None)
    responses = iter([
        "--- a/tests/test_chat.py\n+++ b/tests/test_chat.py\n@@",
        json.dumps({"content": "from chat import chat\n\ndef test_chat():\n    assert chat() == {'reply': 'ok'}\n"}),
    ])
    monkeypatch.setattr(build.llm_service, "chat_completion", lambda *args, **kwargs: SimpleNamespace(content=next(responses)))
    state = {
        "build_run_id": "test",
        "clone_dir": directory,
        "_base_commit": base,
        "plan_data": {
            "feature_request": "Test the chat API route.",
            "tasks": [
                {"file_path": "chat.py", "file_action": "modify"},
                {"file_path": "tests/test_chat.py", "file_action": "create"},
            ],
        },
    }
    build.generate_patches(state)
    assert not state.get("error")
    assert [patch["file_path"] for patch in row.generated_patches] == ["tests/test_chat.py"]
    assert not (tmp_path / "tests" / "test_chat.py").exists()
    build.apply_patches(state)
    assert not state.get("error")
    assert (tmp_path / "tests" / "test_chat.py").is_file()
    assert route.read_text(encoding="utf-8") == "def chat():\n    return {'reply': 'ok'}\n"


@pytest.mark.parametrize("valid_context", [True, False])
def test_patch_applies_only_if_base_context_matches(tmp_path, monkeypatch, valid_context):
    monkeypatch.setattr(build, "_log", lambda *_: None)
    assert build._git("init", cwd=str(tmp_path)).returncode == 0
    target = tmp_path / "route.py"
    target.write_text("return_value = 1\n", encoding="utf-8")
    assert build._git("add", "route.py", cwd=str(tmp_path)).returncode == 0
    old_value = 1 if valid_context else 99
    diff = (
        "--- a/route.py\n+++ b/route.py\n@@ -1 +1 @@\n"
        f"-return_value = {old_value}\n+return_value = 2\n"
    )
    state = {"clone_dir": str(tmp_path), "generated_patches": [{"file_path": "route.py", "diff": diff}]}
    build.apply_patches(state)
    assert bool(state.get("error")) is not valid_context
    assert target.read_text(encoding="utf-8") == f"return_value = {2 if valid_context else 1}\n"


@pytest.mark.parametrize("exit_code", [4, 5])
def test_pytest_usage_error_and_empty_collection_fail_the_gate(tmp_path, monkeypatch, exit_code):
    (tmp_path / "test_route.py").touch()
    monkeypatch.setattr(build, "_log", lambda *_: None)
    monkeypatch.setattr(build, "interrupt", None)
    monkeypatch.setattr(build.settings, "BUILD_PYTHON_TEST_IMAGE", "prepared-test-image")
    monkeypatch.setattr(build, "_git", lambda *args, **kwargs: CompletedProcess(
        args, 0, b"abc123\n" if args[0] == "rev-parse" else b"", b"",
    ))
    monkeypatch.setattr(
        build.subprocess, "run", lambda *args, **kwargs: CompletedProcess(args, exit_code, b"", b"")
    )
    state = {"clone_dir": str(tmp_path), "_docker_available": True}
    build.run_tests(state)
    assert state["test_results"]["exit_code"] == exit_code
    assert state["_retry_count"] == 1


def test_missing_isolated_runner_never_executes_target_tests(tmp_path, monkeypatch):
    (tmp_path / "test_route.py").touch()
    monkeypatch.setattr(build, "_log", lambda *_: None)
    monkeypatch.setattr(build.subprocess, "run", lambda *args, **kwargs: pytest.fail("Unexpected test execution"))
    state = {"clone_dir": str(tmp_path), "_docker_available": False}
    build.run_tests(state)
    assert state["test_results"]["exit_code"] == -1
    assert state["test_results"]["status"] == "not_run"
    assert "No isolated test runner" in state["error"]


def test_eks_runner_receives_tracked_base_and_generated_tests(tmp_path, monkeypatch):
    from app.services import eks_test_runner

    directory = str(tmp_path)
    assert build._git("init", cwd=directory).returncode == 0
    (tmp_path / "service.py").write_text("VALUE = 7\n")
    (tmp_path / "test_service.py").write_text("from service import VALUE\n\ndef test_value():\n    assert VALUE == 7\n")
    assert build._git("add", "--", "service.py", "test_service.py", cwd=directory).returncode == 0
    assert build._git("-c", "user.name=Test", "-c", "user.email=test@example.com",
                      "commit", "-m", "candidate", cwd=directory).returncode == 0
    image = "registry.example/test@" + "sha256:" + "a" * 64
    repository = "example/service"
    monkeypatch.setattr(build.settings, "BUILD_EKS_RUNNER_NAMESPACE", "test-sandbox")
    monkeypatch.setattr(build.settings, "BUILD_EKS_RUNNER_IMAGES", {repository: image})
    monkeypatch.setattr(build, "_log", lambda *_: None)

    def run_archive(namespace, runner_image, snapshot, log):
        assert namespace == "test-sandbox"
        assert runner_image == image
        with tarfile.open(fileobj=io.BytesIO(snapshot), mode="r:gz") as archive:
            assert sorted(archive.getnames()) == ["service.py", "test_service.py"]
            assert b"VALUE = 7" in archive.extractfile("service.py").read()
        return 1, "1 failed, 2 passed in 0.03s"

    monkeypatch.setattr(eks_test_runner, "run_archive", run_archive)
    state = {"clone_dir": directory, "repo_full_name": repository}
    build.run_tests(state)
    assert state["_tested_commit"]
    assert state["test_results"]["exit_code"] == 1
    assert state["test_results"]["failed"] == 1
    assert build._should_continue_after_tests(state) == "generate_patches"


def test_pull_request_stops_when_target_branch_moved(monkeypatch):
    from app.services import repository_client

    commands = []

    def git(*args, **kwargs):
        commands.append(args[0])
        value = b"feature\n" if args[0] == "rev-parse" else b"new-base\trefs/heads/main\n"
        return CompletedProcess(args, 0, value, b"")

    monkeypatch.setattr(build, "_git", git)
    monkeypatch.setattr(build, "_log", lambda *_: None)
    monkeypatch.setattr(repository_client, "RepositoryClient", lambda **_: SimpleNamespace(
        get_clone_info=lambda *_: {"clone_url": "https://github.com/example/service.git", "default_branch": "main"},
    ))
    state = {
        "test_results": {"exit_code": 0, "failed": 0, "errors": 0},
        "_tested_commit": "feature",
        "_base_commit": "old-base",
        "clone_dir": "/unused",
        "branch_name": "forgeai/build-test",
        "repo_full_name": "example/service",
        "org_id": 1,
        "repository_id": 2,
        "user_id": 3,
    }
    build.open_pr(state)
    assert commands == ["rev-parse", "ls-remote"]
    assert "target branch moved" in state["error"]


def test_detect_missing_env_vars():
    raw_output = """
    Traceback (most recent call last):
      File "test_api.py", line 12, in <module>
        KeyError: 'STRIPE_SECRET_KEY'
    pytest error: Missing required environment variable DATABASE_URL
    """
    missing = _detect_missing_env_vars(raw_output)
    assert "STRIPE_SECRET_KEY" in missing
    assert "DATABASE_URL" in missing


def test_has_js_tests():
    with tempfile.TemporaryDirectory() as td:
        assert not _has_js_tests(td)
        test_file = os.path.join(td, "app.test.ts")
        with open(test_file, "w") as f:
            f.write("// test")
        assert _has_js_tests(td)


def test_detect_js_test_runner():
    with tempfile.TemporaryDirectory() as td:
        pkg = os.path.join(td, "package.json")
        with open(pkg, "w") as f:
            f.write('{"scripts": {"test": "vitest run"}}')
        assert _detect_js_test_runner(td) == "vitest"

        with open(pkg, "w") as f:
            f.write('{"devDependencies": {"jest": "^29.0.0"}}')
        assert _detect_js_test_runner(td) == "jest"


def test_extract_test_blocks():
    markdown = """
Here are the missing tests:

`tests/test_calculator.py`
```python
def test_add():
    assert 1 + 1 == 2
```

`tests/test_utils.py`
```python
def test_util():
    assert True
```
"""
    blocks = _extract_test_blocks(markdown)
    assert len(blocks) == 2
    assert blocks[0][0] == "tests/test_calculator.py"
    assert "assert 1 + 1 == 2" in blocks[0][1]
    assert blocks[1][0] == "tests/test_utils.py"


def test_should_continue_after_tests_routing():
    # Passed tests -> open_pr
    state_pass = {
        "test_results": {"exit_code": 0, "failed": 0, "errors": 0},
        "_retry_count": 0,
    }
    assert _should_continue_after_tests(state_pass) == "open_pr"

    # Failed tests with retries left -> generate_patches
    state_fail = {
        "test_results": {"exit_code": 1, "failed": 2, "errors": 0},
        "_retry_count": 1,
    }
    assert _should_continue_after_tests(state_fail) == "generate_patches"

    # Failed tests with max retries exceeded -> open_pr
    state_exhausted = {
        "test_results": {"exit_code": 1, "failed": 2, "errors": 0},
        "_retry_count": MAX_PATCH_RETRIES + 1,
    }
    assert _should_continue_after_tests(state_exhausted) == "open_pr"
