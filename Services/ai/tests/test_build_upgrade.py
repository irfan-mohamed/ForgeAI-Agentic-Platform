"""
Unit tests for ForgeAI Build Execution Graph upgrades:
  - Strict patch application and integration-test exit handling
  - JS/TS test detection (_has_js_tests, _detect_js_test_runner)
  - Missing env var detection (_detect_missing_env_vars)
  - Test block extraction from testing_agent markdown (_extract_test_blocks)
  - Retry loop routing (_should_continue_after_tests)
"""
import os
import tempfile
from subprocess import CompletedProcess
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
    assert "No isolated test runner" in state["error"]


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
