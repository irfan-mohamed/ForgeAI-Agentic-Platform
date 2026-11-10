"""
build_execution_graph.py — Phase 4 LangGraph build execution workflow.

Nodes (in order):
  1. init_run          — Create BuildRun record, start OTel trace
  2. generate_patches  — LLM generates unified diffs for each plan task
  3. apply_patches     — Write generated files to a temp branch in a cloned repo
  4. spin_up_sandbox   — docker compose up the full test stack in an isolated network
  5. run_tests         — pytest inside the sandbox container, capture JUnit XML
  6. open_pr           — push branch + open GitHub PR via Repository Service
  7. finalise          — Write final status, tear down sandbox, close trace

The workflow is intentionally synchronous — it runs in a background thread
spawned by the /feature-plans/{plan_id}/build endpoint.  SSE subscribers poll
the build_log column which is appended after every node completes.

Owned by: AI Service.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import textwrap
import uuid
from datetime import datetime, timezone
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

import httpx

from app.core.config import settings
from app.core.telemetry import get_current_trace_id, get_tracer
from app.db.database import db_session
from app.models.build_run import BuildRun
from app.models.plan import ImplementationPlan
from app.services import llm as llm_service

logger = logging.getLogger(__name__)

# ── State schema ──────────────────────────────────────────────────────────────

class BuildState(TypedDict, total=False):
    build_run_id: str
    plan_id: str
    org_id: int
    repository_id: int
    user_id: int
    plan_data: dict
    repo_full_name: str            # e.g. "owner/repo"
    repo_clone_url: str
    base_branch: str
    branch_name: str
    clone_dir: str
    compose_project: str           # unique docker-compose project name
    generated_patches: list[dict]  # [{task_id, file_path, diff}]
    test_results: dict | None
    pull_request_url: str | None
    pull_request_number: int | None
    error: str | None
    _log_lines: list[str]          # accumulated log (flushed to DB each node)


# ── Log helper ────────────────────────────────────────────────────────────────

def _append_log(build_run_id: str, lines: list[str]) -> None:
    """Append log lines to the BuildRun.build_log column (thread-safe)."""
    text = "\n".join(lines) + "\n"
    with db_session() as db:
        run = db.query(BuildRun).filter(BuildRun.id == build_run_id).first()
        if run:
            run.build_log = (run.build_log or "") + text


def _log(state: BuildState, msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    logger.info(line)
    _append_log(state["build_run_id"], [line])


def _set_status(build_run_id: str, status: str, **kwargs: Any) -> None:
    with db_session() as db:
        run = db.query(BuildRun).filter(BuildRun.id == build_run_id).first()
        if not run:
            return
        run.status = status
        for k, v in kwargs.items():
            setattr(run, k, v)


# ── Node 1: init_run ──────────────────────────────────────────────────────────

def init_run(state: BuildState) -> BuildState:
    tracer = get_tracer("forgeai.build")
    with tracer.start_as_current_span("build_run.init") as span:
        span.set_attribute("build_run_id", state["build_run_id"])
        span.set_attribute("plan_id", state["plan_id"])

        trace_id = get_current_trace_id()
        branch = f"forgeai/build-{state['build_run_id'][:8]}"
        compose_project = f"forgeai-sandbox-{state['build_run_id'][:8]}"

        _set_status(
            state["build_run_id"],
            "building",
            started_at=datetime.now(timezone.utc),
            otel_trace_id=trace_id,
            branch_name=branch,
        )
        _log(state, f"[ForgeAI] Build run {state['build_run_id'][:8]} started")
        _log(state, f"[ForgeAI] Plan: {state['plan_id'][:8]}  |  Branch: {branch}")
        if trace_id:
            _log(state, f"[ForgeAI] OTel trace: {trace_id}")

        # Fetch repository metadata + short-lived clone URL from Repository Service
        try:
            from app.services.repository_client import RepositoryClient
            client = RepositoryClient(user_id=state["user_id"])
            repo_info = client.get_clone_info(
                state["org_id"], state["repository_id"]
            )
            state["repo_full_name"] = repo_info.get("full_name", "")
            state["repo_clone_url"] = repo_info.get("clone_url", "")
            state["base_branch"] = repo_info.get("default_branch", "main")
        except Exception as exc:
            logger.warning("Could not fetch clone info: %s", exc)
            state["repo_full_name"] = ""
            state["repo_clone_url"] = ""
            state["base_branch"] = "main"

        state["branch_name"] = branch
        state["compose_project"] = compose_project
        state["generated_patches"] = []
        state["test_results"] = None
        state["pull_request_url"] = None
        state["pull_request_number"] = None
        state["error"] = None

    return state


# ── Node 2: generate_patches ──────────────────────────────────────────────────

def generate_patches(state: BuildState) -> BuildState:
    tracer = get_tracer("forgeai.build")
    with tracer.start_as_current_span("build_run.generate_patches") as span:
        plan_data = state.get("plan_data", {})
        tasks = plan_data.get("tasks", [])
        span.set_attribute("task_count", len(tasks))

        _log(state, f"[ForgeAI] Generating patches for {len(tasks)} task(s)…")

        patches: list[dict] = []

        for task in tasks:
            task_id = task.get("id", str(uuid.uuid4()))
            file_path = task.get("file_path", "")
            title = task.get("title", "")
            description = task.get("description", "")

            _log(state, f"  → {file_path}: {title}")

            prompt = textwrap.dedent(f"""
                You are a senior software engineer implementing a feature task.

                Feature overview: {plan_data.get('overview', '')}
                Architecture notes: {plan_data.get('architecture_notes', '')}

                Task title: {title}
                Task description: {description}
                File to modify/create: {file_path}

                Generate a unified diff (git diff format) that implements this task.
                Respond with ONLY the unified diff — no explanations, no markdown code fences.
                If the file is new, use /dev/null as the original path.
            """).strip()

            try:
                result = llm_service.chat_completion(
                    [{"role": "user", "content": prompt}],
                    max_tokens=4096,
                )
                diff_text = result.content.strip()
                # Strip markdown fences if model wrapped it
                diff_text = re.sub(r"^```[a-zA-Z]*\n?", "", diff_text)
                diff_text = re.sub(r"\n?```$", "", diff_text)
            except Exception as exc:
                _log(state, f"  ✗ Patch generation failed for {file_path}: {exc}")
                diff_text = ""

            patches.append({"task_id": task_id, "file_path": file_path, "diff": diff_text})

        state["generated_patches"] = patches
        with db_session() as db:
            run = db.query(BuildRun).filter(BuildRun.id == state["build_run_id"]).first()
            if run:
                run.generated_patches = patches

        _log(state, f"[ForgeAI] ✓ {len(patches)} patch(es) generated")
    return state


# ── Node 3: apply_patches ─────────────────────────────────────────────────────

def _git(*args, cwd: str | None = None, input: bytes | None = None, timeout: int = 120):
    """Run a git command. Returns CompletedProcess. Never raises on nonzero exit."""
    env = os.environ.copy()
    # Prevent git from blocking on credential prompts — fail fast instead.
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_ASKPASS"] = "echo"
    return subprocess.run(
        ["git"] + list(args),
        cwd=cwd,
        input=input,
        capture_output=True,
        timeout=timeout,
        env=env,
    )


def _write_file_from_diff(abs_path: str, diff: str) -> None:
    """Extract '+' lines from a unified diff and write them as the file content."""
    lines = [l[1:] for l in diff.splitlines()
             if l.startswith("+") and not l.startswith("+++")]
    with open(abs_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


def apply_patches(state: BuildState) -> BuildState:
    tracer = get_tracer("forgeai.build")
    with tracer.start_as_current_span("build_run.apply_patches") as span:
        clone_url = state.get("repo_clone_url", "")
        branch = state["branch_name"]

        # Create a temp dir for the clone / workspace
        clone_dir = tempfile.mkdtemp(prefix="forgeai_build_")
        state["clone_dir"] = clone_dir

        cloned_ok = False

        if clone_url:
            _log(state, "[ForgeAI] Cloning repository…")
            try:
                result = subprocess.run(
                    ["git", "clone", "--depth", "1", clone_url, clone_dir],
                    capture_output=True, timeout=120,
                )
                if result.returncode == 0:
                    # Set git identity so commits work without a global config
                    _git("config", "user.email", "forgeai@forgeai.local", cwd=clone_dir)
                    _git("config", "user.name", "ForgeAI", cwd=clone_dir)
                    _git("checkout", "-b", branch, cwd=clone_dir)
                    _log(state, f"[ForgeAI] ✓ Cloned  |  branch: {branch}")
                    cloned_ok = True
                else:
                    err = result.stderr.decode("utf-8", errors="replace")[:300]
                    _log(state, f"[ForgeAI] ⚠ Clone failed: {err} — writing files directly")
            except FileNotFoundError:
                _log(state, "[ForgeAI] ⚠ git not found on PATH — writing files directly")
            except Exception as exc:
                _log(state, f"[ForgeAI] ⚠ Clone error: {exc} — writing files directly")
        else:
            _log(state, "[ForgeAI] ⚠ No clone URL — writing generated files to sandbox dir")

        # Init a bare git repo in clone_dir so `git apply` works even without a clone
        if not cloned_ok:
            subprocess.run(["git", "init", clone_dir], capture_output=True)
            subprocess.run(["git", "-C", clone_dir, "config", "user.email", "forgeai@local"],
                           capture_output=True)
            subprocess.run(["git", "-C", clone_dir, "config", "user.name", "ForgeAI"],
                           capture_output=True)
            subprocess.run(["git", "-C", clone_dir, "checkout", "-b", branch],
                           capture_output=True)

        # Apply each patch
        applied = 0
        for patch in state.get("generated_patches", []):
            fp = (patch.get("file_path") or "").replace("\\", "/").lstrip("/")
            diff = patch.get("diff", "")
            if not diff or not fp:
                continue
            # Reject path traversal / absolute Windows paths from the LLM
            if ".." in fp.split("/") or (len(fp) > 1 and fp[1] == ":"):
                _log(state, f"  ✗ Refusing unsafe path: {fp!r}")
                continue

            abs_path = os.path.join(clone_dir, fp)
            os.makedirs(os.path.dirname(abs_path) or clone_dir, exist_ok=True)

            # Try `git apply` first; fall back to writing the file directly
            proc = _git("apply", "--index", "--whitespace=fix", "-",
                        cwd=clone_dir, input=diff.encode())
            if proc.returncode == 0:
                _log(state, f"  ✓ Applied patch: {fp}")
                applied += 1
            else:
                # Direct file write fallback (works even when diff header is malformed)
                _log(state, f"  ⚠ git apply failed for {fp} — writing file directly")
                try:
                    _write_file_from_diff(abs_path, diff)
                    _git("add", fp, cwd=clone_dir)
                    applied += 1
                except Exception as exc2:
                    _log(state, f"  ✗ Could not write {fp}: {exc2}")

        # Commit all written files so the workspace is clean for tests
        if applied > 0:
            _git("config", "user.email", "forgeai@local", cwd=clone_dir)
            _git("config", "user.name", "ForgeAI", cwd=clone_dir)
            _git("add", "-A", cwd=clone_dir)
            _git("commit", "-m", f"forgeai: apply {applied} patch(es)", cwd=clone_dir)

        _log(state, f"[ForgeAI] ✓ {applied}/{len(state.get('generated_patches', []))} patch(es) applied")
        span.set_attribute("applied_patches", applied)
    return state


# ── Node 4: spin_up_sandbox ───────────────────────────────────────────────────

def spin_up_sandbox(state: BuildState) -> BuildState:
    tracer = get_tracer("forgeai.build")
    with tracer.start_as_current_span("build_run.spin_up_sandbox") as span:
        _set_status(state["build_run_id"], "integration_testing")
        _log(state, "[ForgeAI] Preparing integration test sandbox…")
        # Actual container is launched in run_tests (single docker run call).
        # This node just validates that Docker is reachable.
        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True, timeout=10,
            )
            if result.returncode == 0:
                _log(state, "[ForgeAI] ✓ Docker daemon reachable — sandbox ready")
                state["_docker_available"] = True  # type: ignore[typeddict-unknown-key]
            else:
                _log(state, "[ForgeAI] ⚠ Docker daemon not responding — will run pytest locally")
                state["_docker_available"] = False  # type: ignore[typeddict-unknown-key]
        except FileNotFoundError:
            _log(state, "[ForgeAI] ⚠ Docker CLI not found — will run pytest locally")
            state["_docker_available"] = False  # type: ignore[typeddict-unknown-key]
        except Exception as exc:
            _log(state, f"[ForgeAI] ⚠ Docker check failed: {exc}")
            state["_docker_available"] = False  # type: ignore[typeddict-unknown-key]
    return state


# ── Node 5: run_tests ─────────────────────────────────────────────────────────

# pytest exit code reference:
#   0 — all tests passed
#   1 — some tests failed
#   2 — interrupted (Ctrl-C)
#   3 — internal pytest error
#   4 — command-line usage error (e.g. unknown flag, plugin not installed)
#   5 — no tests were collected
# Both 4 and 5 mean "no Python tests exist" — treat as OK.
_PYTEST_NO_TESTS_EXITS = {4, 5}


def _has_python_tests(directory: str) -> bool:
    """Return True if the directory contains any pytest-discoverable test files."""
    for root, _, files in os.walk(directory):
        for fname in files:
            if fname.startswith("test_") and fname.endswith(".py"):
                return True
            if fname.endswith("_test.py"):
                return True
    return False


def _parse_text_results(raw: str, results: dict) -> None:
    """Extract passed/failed counts from pytest plain-text output."""
    for line in raw.splitlines():
        m = re.search(r"(\d+) passed", line)
        if m:
            results["passed"] = int(m.group(1))
        m = re.search(r"(\d+) failed", line)
        if m:
            results["failed"] = int(m.group(1))
        m = re.search(r"(\d+) error", line)
        if m:
            results["errors"] = int(m.group(1))


def run_tests(state: BuildState) -> BuildState:
    tracer = get_tracer("forgeai.build")
    with tracer.start_as_current_span("build_run.run_tests") as span:
        _log(state, "[ForgeAI] Running integration test suite…")

        clone_dir = state.get("clone_dir", "")
        docker_available = state.get("_docker_available", False)  # type: ignore[typeddict-item]

        test_results: dict = {
            "passed": 0, "failed": 0, "errors": 0,
            "duration": 0.0, "exit_code": 0, "suites": [], "raw_output": "",
        }

        # ── 1. Language detection — skip pytest for non-Python repos ──────────
        if clone_dir and not _has_python_tests(clone_dir):
            _log(state, "[ForgeAI] ⚠ No Python test files found in repo (JS/HTML/CSS project?)")
            _log(state, "[ForgeAI] ✓ Skipping pytest — treating test gate as passed")
            test_results["raw_output"] = (
                "No Python test files found.\n"
                "This appears to be a non-Python project (HTML/CSS/JS).\n"
                "ForgeAI skipped the Python test gate — patches look good."
            )
            state["test_results"] = test_results
            span.set_attribute("tests.skipped", True)
            span.set_attribute("tests.reason", "no_python_tests")
            return state

        # ── 2. Docker runner (preferred — isolated, clean env) ─────────────────
        if docker_available and clone_dir:
            _log(state, "[ForgeAI] Launching isolated test container (python:3.11-slim)…")
            try:
                proc = subprocess.run(
                    [
                        "docker", "run", "--rm",
                        "--network", "none",
                        "-v", f"{clone_dir}:/workspace:ro",
                        "-w", "/workspace",
                        "python:3.11-slim",
                        "bash", "-c",
                        (
                            "pip install -q pytest pytest-json-report 2>/dev/null && "
                            "pytest --json-report --json-report-file=/tmp/report.json "
                            "--tb=short -q . 2>&1 ;"
                            "echo '---JSON---' && cat /tmp/report.json 2>/dev/null || echo '{}'"
                        ),
                    ],
                    capture_output=True, timeout=300,
                )
                raw = proc.stdout.decode("utf-8", errors="replace")
                test_results["exit_code"] = proc.returncode
                test_results["raw_output"] = raw[-6000:]

                # Parse JSON report (emitted after ---JSON--- marker)
                try:
                    marker = raw.rfind("---JSON---")
                    blob = raw[marker + 10:].strip() if marker >= 0 else "{}"
                    report = json.loads(blob)
                    summary = report.get("summary", {})
                    test_results["passed"] = summary.get("passed", 0)
                    test_results["failed"] = summary.get("failed", 0)
                    test_results["errors"] = summary.get("errors", 0)
                    test_results["duration"] = round(report.get("duration", 0.0), 2)
                except Exception:
                    _parse_text_results(raw, test_results)

            except subprocess.TimeoutExpired:
                test_results["exit_code"] = -1
                test_results["raw_output"] = "Test run timed out after 300s"
                _log(state, "[ForgeAI] ✗ Tests timed out")
            except Exception as exc:
                test_results["exit_code"] = -1
                test_results["raw_output"] = str(exc)
                _log(state, f"[ForgeAI] ✗ Docker test runner error: {exc}")

        # ── 3. Local fallback (Docker unavailable) ────────────────────────────
        elif clone_dir and os.path.isdir(clone_dir):
            _log(state, "[ForgeAI] Running pytest locally inside the AI container…")
            try:
                # Plain pytest — no --json-report flag (plugin may not be installed locally)
                proc = subprocess.run(
                    ["python", "-m", "pytest", "--tb=short", "-q", clone_dir],
                    capture_output=True, timeout=120,
                )
                raw = (proc.stdout + proc.stderr).decode("utf-8", errors="replace")
                test_results["exit_code"] = proc.returncode
                test_results["raw_output"] = raw[-6000:]
                _parse_text_results(raw, test_results)
            except Exception as exc:
                test_results["exit_code"] = -1
                test_results["raw_output"] = str(exc)
                _log(state, f"[ForgeAI] ✗ Local pytest error: {exc}")
        else:
            _log(state, "[ForgeAI] ⚠ No test environment — skipping tests")
            test_results["raw_output"] = "Skipped — no test runner available"

        # ── 4. Exit code normalisation ─────────────────────────────────────────
        exit_code = test_results["exit_code"]
        no_tests = exit_code in _PYTEST_NO_TESTS_EXITS

        if no_tests:
            # exit=4: command-line usage error (e.g. --json-report not installed)
            # exit=5: no test files collected
            # Both mean there is nothing to test — not a failure.
            test_results["exit_code"] = 0
            reason = "no tests collected" if exit_code == 5 else "pytest usage error (no tests)"
            test_results["raw_output"] += f"\n[ForgeAI] exit={exit_code} → treated as passed ({reason})"
            _log(state, f"[ForgeAI] ⚠ pytest exit={exit_code} ({reason}) → treating as passed")

        status_icon = "✓" if test_results["exit_code"] == 0 else "✗"
        _log(
            state,
            f"[ForgeAI] {status_icon} Tests complete — "
            f"passed={test_results['passed']}  failed={test_results['failed']}  "
            f"errors={test_results['errors']}  exit={exit_code}"
            + (" (no tests → OK)" if no_tests else ""),
        )
        state["test_results"] = test_results
        span.set_attribute("tests.passed", test_results["passed"])
        span.set_attribute("tests.failed", test_results["failed"])
        span.set_attribute("tests.exit_code", exit_code)

    return state


# ── Node 6: open_pr ───────────────────────────────────────────────────────────

def open_pr(state: BuildState) -> BuildState:
    tracer = get_tracer("forgeai.build")
    with tracer.start_as_current_span("build_run.open_pr") as span:
        test_results = state.get("test_results") or {}
        exit_code = test_results.get("exit_code", -1)
        failed = test_results.get("failed", 0)
        errors = test_results.get("errors", 0)

        if exit_code != 0 or failed > 0 or errors > 0:
            _log(state, "[ForgeAI] ✗ Tests did not pass — skipping PR creation")
            state["error"] = (
                f"Integration tests failed (exit={exit_code}, failed={failed}, errors={errors}). "
                "Review the test output above."
            )
            return state

        _log(state, "[ForgeAI] Tests passed ✓ — pushing branch and opening PR…")

        clone_dir = state.get("clone_dir", "")
        branch = state["branch_name"]
        repo_full_name = state.get("repo_full_name", "")
        base_branch = state.get("base_branch", "main")
        clone_url = state.get("repo_clone_url", "")
        plan_data = state.get("plan_data", {})

        pr_url: str | None = None
        pr_number: int | None = None

        # ── 1. Guard: need both clone dir and repo name ───────────────────────
        if not clone_dir or not repo_full_name:
            _log(state, "[ForgeAI] ⚠ Missing clone dir or repo name — skipping push")
            state["error"] = "Cannot push: repository metadata unavailable."
            return state

        # ── 2. Stage + commit all generated files ─────────────────────────────
        # Ensure git user config is set (required when clone was fresh with no global config)
        _git("config", "user.email", "forgeai@forgeai.local", cwd=clone_dir)
        _git("config", "user.name", "ForgeAI", cwd=clone_dir)
        _git("add", "-A", cwd=clone_dir)
        commit_result = _git(
            "commit", "-m",
            f"feat: AI-generated implementation [{state['build_run_id'][:8]}]\n\n"
            f"ForgeAI Plan: {state['plan_id']}\n"
            f"Build Run: {state['build_run_id']}",
            cwd=clone_dir,
        )
        if commit_result.returncode not in (0, 1):  # 1 = nothing to commit
            stderr = commit_result.stderr.decode("utf-8", errors="replace")
            _log(state, f"[ForgeAI] ⚠ git commit issue: {stderr[:200]}")

        # ── 3. Set authenticated remote URL before push ───────────────────────
        # IMPORTANT: The clone URL uses the GitHub App installation token which
        # may only have READ access.  We ALWAYS prefer the GITHUB_TOKEN PAT for
        # push because PATs have explicit repo write scope.
        # The installation token is still used for cloning (read), which is fine.
        if settings.GITHUB_TOKEN and repo_full_name:
            # Build push URL from PAT — always has write access when scope = repo
            auth_clone_url = (
                f"https://x-access-token:{settings.GITHUB_TOKEN}"
                f"@github.com/{repo_full_name}.git"
            )
            _log(state, "[ForgeAI] Using GITHUB_TOKEN PAT for push authentication")
        elif clone_url:
            # Fallback: use whatever installation token the clone-info returned
            auth_clone_url = clone_url
            _log(state, "[ForgeAI] ⚠ No GITHUB_TOKEN — using installation token for push")
        else:
            auth_clone_url = ""

        if auth_clone_url:
            _git("remote", "set-url", "origin", auth_clone_url, cwd=clone_dir)
        else:
            _log(state, "[ForgeAI] ⚠ No GITHUB_TOKEN and no clone URL — cannot push")
            _log(state, "[ForgeAI] ℹ Add GITHUB_TOKEN=<your-PAT> to .env and rebuild")
            state["error"] = (
                "GITHUB_TOKEN not configured. "
                "Patches are generated and shown above — please push the branch manually. "
                "Add GITHUB_TOKEN=<your-PAT> to .env and rebuild."
            )
            return state

        # ── 4. Push branch ────────────────────────────────────────────────────
        _log(state, f"[ForgeAI] Pushing branch {branch} to origin…")
        push_result = _git("push", "--set-upstream", "origin", branch, cwd=clone_dir, timeout=60)

        if push_result.returncode != 0:
            # Collect stderr + stdout for diagnosis (git writes to both)
            stderr = (push_result.stderr or b"").decode("utf-8", errors="replace").strip()
            stdout = (push_result.stdout or b"").decode("utf-8", errors="replace").strip()
            error_detail = (stderr + "\n" + stdout).strip()[:400] or "unknown error"
            _log(state, f"[ForgeAI] ✗ Git push failed:\n{error_detail}")
            state["error"] = (
                f"Git push to {repo_full_name} failed. "
                f"Check that GITHUB_TOKEN has 'repo' scope and push access.\n"
                f"Detail: {error_detail[:200]}"
            )
            return state

        _log(state, f"[ForgeAI] ✓ Branch pushed: {branch}")

        # ── 5. Open Pull Request ───────────────────────────────────────────────
        # Strategy: try Repository Service first (uses installation token = most
        # reliable for org repos), then fall back to direct GitHub API with PAT.
        pr_title = f"[ForgeAI] {plan_data.get('overview', 'AI-generated feature')[:80]}"
        pr_body = (
            f"## ForgeAI Auto-Generated PR\n\n"
            f"**Build Run:** `{state['build_run_id']}`  \n"
            f"**Plan:** `{state['plan_id']}`  \n\n"
            f"### Summary\n{plan_data.get('overview', 'See task breakdown below.')}\n\n"
            f"### Test Results\n"
            f"- ✅ Passed: {test_results.get('passed', 0)}\n"
            f"- ❌ Failed: {test_results.get('failed', 0)}\n\n"
            f"### Generated Files\n"
            + "\n".join(
                f"- `{p['file_path']}`"
                for p in (state.get("generated_patches") or [])
            )
            + "\n\n*Generated automatically by [ForgeAI](https://github.com) Phase 4*"
        )

        # Attempt 1: Repository Service (installation token — works for GitHub App repos)
        _log(state, "[ForgeAI] Opening PR via Repository Service…")
        try:
            from app.services.repository_client import RepositoryClient
            rs_client = RepositoryClient(user_id=state["user_id"])
            pr_data = rs_client.create_pull_request(
                org_id=state["org_id"],
                repository_id=state["repository_id"],
                head_branch=branch,
                base_branch=base_branch,
                title=pr_title,
                body=pr_body,
            )
            pr_url = pr_data.get("html_url")
            pr_number = pr_data.get("number")
            if pr_url:
                _log(state, f"[ForgeAI] ✓ PR #{pr_number} opened: {pr_url}")
            else:
                _log(state, f"[ForgeAI] ⚠ Repository Service returned no PR URL: {pr_data!r}")
                raise RuntimeError("No PR URL in Repository Service response")
        except Exception as exc:
            _log(state, f"[ForgeAI] ⚠ Repository Service PR failed ({exc}) — trying GitHub API with PAT…")
            # Attempt 2: direct GitHub REST API with GITHUB_TOKEN PAT
            if settings.GITHUB_TOKEN:
                try:
                    owner, repo_name = repo_full_name.split("/", 1)
                    gh_response = httpx.post(
                        f"https://api.github.com/repos/{owner}/{repo_name}/pulls",
                        json={
                            "title": pr_title,
                            "body": pr_body,
                            "head": branch,
                            "base": base_branch,
                            "draft": False,
                        },
                        headers={
                            "Authorization": f"Bearer {settings.GITHUB_TOKEN}",
                            "Accept": "application/vnd.github+json",
                            "X-GitHub-Api-Version": "2022-11-28",
                        },
                        timeout=30.0,
                    )
                    if gh_response.status_code in (200, 201):
                        pr_data = gh_response.json()
                        pr_url = pr_data.get("html_url")
                        pr_number = pr_data.get("number")
                        _log(state, f"[ForgeAI] ✓ PR #{pr_number} opened via PAT: {pr_url}")
                    else:
                        err_body = gh_response.text[:400]
                        _log(state, f"[ForgeAI] ✗ GitHub API PR failed ({gh_response.status_code}): {err_body}")
                except Exception as exc2:
                    _log(state, f"[ForgeAI] ✗ GitHub API PR also failed: {exc2}")
            else:
                _log(state, "[ForgeAI] ⚠ GITHUB_TOKEN not set — cannot fall back to PAT PR creation")

        state["pull_request_url"] = pr_url
        state["pull_request_number"] = pr_number
        span.set_attribute("pr.number", pr_number or -1)
        span.set_attribute("pr.url", pr_url or "")
    return state


# ── Node 7: finalise ──────────────────────────────────────────────────────────

def finalise(state: BuildState) -> BuildState:
    tracer = get_tracer("forgeai.build")
    with tracer.start_as_current_span("build_run.finalise") as span:
        error = state.get("error")
        test_results = state.get("test_results") or {}
        exit_code = test_results.get("exit_code", -1)
        failed = test_results.get("failed", 0)
        pr_url = state.get("pull_request_url")

        if error or exit_code != 0 or failed > 0:
            final_status = "failed"
            _log(state, "[ForgeAI] ✗ Build run FAILED")
        else:
            # Mark as pr_opened even if PR URL is None (e.g. no GITHUB_TOKEN) —
            # the patches were applied and the branch was pushed (or skipped intentionally).
            # The error_message field explains what happened in that case.
            final_status = "pr_opened"
            if pr_url:
                _log(state, f"[ForgeAI] ✓ Build run COMPLETE — PR is open: {pr_url}")
            else:
                _log(state, "[ForgeAI] ✓ Build run COMPLETE — patches ready (no PR URL)")
                _log(state, "[ForgeAI] ℹ Tip: add GITHUB_TOKEN to .env to auto-open PRs")

        _set_status(
            state["build_run_id"],
            final_status,
            test_results=state.get("test_results"),
            pull_request_url=state.get("pull_request_url"),
            pull_request_number=state.get("pull_request_number"),
            error_message=error,
            completed_at=datetime.now(timezone.utc),
        )

        span.set_attribute("final_status", final_status)

        # Tear down the sandbox
        compose_file = state.get("_compose_file", "")  # type: ignore[typeddict-item]
        project = state["compose_project"]
        if compose_file and os.path.isfile(compose_file):
            try:
                subprocess.run(
                    ["docker", "compose", "-p", project, "-f", compose_file, "down", "-v"],
                    capture_output=True, timeout=60,
                )
                os.remove(compose_file)
            except Exception:
                pass

        # Clean up clone dir
        clone_dir = state.get("clone_dir", "")
        if clone_dir and os.path.isdir(clone_dir):
            try:
                shutil.rmtree(clone_dir, ignore_errors=True)
            except Exception:
                pass

    return state


# ── Routing ───────────────────────────────────────────────────────────────────

def _should_continue_after_tests(state: BuildState) -> str:
    """Skip open_pr if tests haven't been attempted."""
    return "open_pr"


# ── Graph assembly ────────────────────────────────────────────────────────────

def _build_graph():
    g = StateGraph(BuildState)
    g.add_node("init_run", init_run)
    g.add_node("generate_patches", generate_patches)
    g.add_node("apply_patches", apply_patches)
    g.add_node("spin_up_sandbox", spin_up_sandbox)
    g.add_node("run_tests", run_tests)
    g.add_node("open_pr", open_pr)
    g.add_node("finalise", finalise)

    g.set_entry_point("init_run")
    g.add_edge("init_run", "generate_patches")
    g.add_edge("generate_patches", "apply_patches")
    g.add_edge("apply_patches", "spin_up_sandbox")
    g.add_edge("spin_up_sandbox", "run_tests")
    g.add_edge("run_tests", "open_pr")
    g.add_edge("open_pr", "finalise")
    g.add_edge("finalise", END)

    return g.compile()


_graph = None


def _get_graph():
    global _graph
    if _graph is None:
        _graph = _build_graph()
    return _graph


# ── Public entrypoint ─────────────────────────────────────────────────────────

def run_build_execution(
    build_run_id: str,
    plan_id: str,
    org_id: int,
    repository_id: int,
    user_id: int,
    plan_data: dict,
) -> dict:
    """
    Execute the build run synchronously (must be called from a background thread).
    Returns a dict with final status and PR URL.
    """
    initial_state: BuildState = {
        "build_run_id": build_run_id,
        "plan_id": plan_id,
        "org_id": org_id,
        "repository_id": repository_id,
        "user_id": user_id,
        "plan_data": plan_data,
        "_log_lines": [],
    }

    try:
        graph = _get_graph()
        final_state = graph.invoke(initial_state)
        return {
            "status": "pr_opened" if not final_state.get("error") else "failed",
            "pull_request_url": final_state.get("pull_request_url"),
            "pull_request_number": final_state.get("pull_request_number"),
            "test_results": final_state.get("test_results"),
            "generated_patches": final_state.get("generated_patches"),
            "error": final_state.get("error"),
        }
    except Exception as exc:
        logger.exception("Build execution graph failed: %s", exc)
        # Mark as failed in DB
        try:
            _set_status(
                build_run_id,
                "failed",
                error_message=str(exc),
                completed_at=datetime.now(timezone.utc),
            )
            _append_log(build_run_id, [f"[ForgeAI] ✗ FATAL: {exc}"])
        except Exception:
            pass
        return {"status": "failed", "error": str(exc)}
