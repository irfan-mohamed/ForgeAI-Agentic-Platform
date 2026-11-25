"""
Unit tests for ForgeAI Build Execution Graph upgrades:
  - Better diff application (_apply_diff_to_file)
  - JS/TS test detection (_has_js_tests, _detect_js_test_runner)
  - Missing env var detection (_detect_missing_env_vars)
  - Test block extraction from testing_agent markdown (_extract_test_blocks)
  - Retry loop routing (_should_continue_after_tests)
"""
import os
import tempfile
import pytest

from app.services.build_execution_graph import (
    _apply_diff_to_file,
    _detect_js_test_runner,
    _detect_missing_env_vars,
    _extract_test_blocks,
    _has_js_tests,
    _should_continue_after_tests,
    MAX_PATCH_RETRIES,
)


def test_apply_diff_to_new_file():
    with tempfile.TemporaryDirectory() as td:
        target = os.path.join(td, "new_file.py")
        diff = """--- /dev/null
+++ b/new_file.py
@@ -0,0 +1,3 @@
+def hello():
+    return 'world'
"""
        _apply_diff_to_file(target, diff)
        assert os.path.isfile(target)
        with open(target, "r", encoding="utf-8") as f:
            content = f.read()
        assert "def hello():" in content
        assert "return 'world'" in content


def test_apply_diff_to_existing_file():
    with tempfile.TemporaryDirectory() as td:
        target = os.path.join(td, "mod.py")
        with open(target, "w", encoding="utf-8") as f:
            f.write("def foo():\n    return 1\n")

        diff = """--- a/mod.py
+++ b/mod.py
@@ -1,2 +1,2 @@
 def foo():
-    return 1
+    return 42
"""
        _apply_diff_to_file(target, diff)
        with open(target, "r", encoding="utf-8") as f:
            content = f.read()
        assert "return 42" in content
        assert "return 1" not in content


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
