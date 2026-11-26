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
from pathlib import Path, PurePosixPath
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

try:
    from langgraph.types import Command, interrupt
except ImportError:
    interrupt = None
    Command = None

import httpx

from app.core.config import settings
from app.core.telemetry import get_current_trace_id, get_tracer
from app.db.database import db_session
from app.models.build_run import BuildRun
from app.models.plan import ImplementationPlan
from app.services import llm as llm_service

logger = logging.getLogger(__name__)

MAX_PATCH_RETRIES = 2

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
    _network_mode: str             # "none" | "bridge"
    _retry_count: int              # patch-regen attempt counter
    _failed_test_output: str       # last failing test output
    _generated_test_files: list[dict]
    _base_commit: str
    _docker_available: bool
    env_vars: dict                 # {VAR_NAME: value} injected into test container
    interrupt_payload: dict


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
        plan_data_local = state.get("plan_data", {})
        state["_network_mode"] = "bridge" if plan_data_local.get("requires_network", False) else "none"
        _log(state, f"[ForgeAI] Network mode: {state['_network_mode']}")
        state["_retry_count"] = 0
        state["_failed_test_output"] = ""
        state["env_vars"] = state.get("env_vars") or {}
        state["generated_patches"] = []
        state["test_results"] = None
        state["pull_request_url"] = None
        state["pull_request_number"] = None
        state["error"] = None

    return state


# ── Node 2: generate_patches ──────────────────────────────────────────────────

def _workspace_path(directory: str, path: str) -> Path:
    relative = PurePosixPath(path)
    root = Path(directory).resolve()
    target = root / relative
    if (
        not path or relative.is_absolute() or ":" in path or "\\" in path
        or {".git", ".."}.intersection(relative.parts)
        or target == root or not target.resolve().is_relative_to(root)
    ):
        raise ValueError("Expected a safe repository-relative path.")
    return target


def _checkout_base(state: BuildState) -> str:
    if state.get("_base_commit"):
        clone_dir = state["clone_dir"]
        if _git("reset", "--hard", state["_base_commit"], cwd=clone_dir).returncode:
            raise RuntimeError("Could not reset the build checkout.")
        return clone_dir

    if not state.get("repo_clone_url"):
        raise RuntimeError("Repository clone URL is unavailable.")
    clone_dir = tempfile.mkdtemp(prefix="forgeai_build_")
    state["clone_dir"] = clone_dir
    _log(state, "[ForgeAI] Cloning the repository base branch…")
    if _git("clone", "--depth", "1", "--branch", state["base_branch"], "--",
            state["repo_clone_url"], clone_dir).returncode:
        raise RuntimeError("Could not clone the repository base branch.")
    revision = _git("rev-parse", "HEAD", cwd=clone_dir)
    if revision.returncode or _git("checkout", "-b", state["branch_name"], cwd=clone_dir).returncode:
        raise RuntimeError("Could not prepare the build branch.")
    if _git("remote", "set-url", "origin", f"https://github.com/{state['repo_full_name']}.git",
            cwd=clone_dir).returncode:
        raise RuntimeError("Could not remove clone credentials from the workspace.")
    state["_base_commit"] = revision.stdout.decode().strip()
    return clone_dir


def generate_patches(state: BuildState) -> BuildState:
    tracer = get_tracer("forgeai.build")
    with tracer.start_as_current_span("build_run.generate_patches") as span:
        plan_data = state.get("plan_data", {})
        tasks = plan_data.get("tasks", [])
        span.set_attribute("task_count", len(tasks))

        _log(state, f"[ForgeAI] Generating patches for {len(tasks)} task(s)…")

        patches: list[dict] = []
        state["generated_patches"] = patches
        state["_generated_test_files"] = []
        try:
            clone_dir = _checkout_base(state)
        except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
            state["error"] = str(exc)
            _log(state, f"[ForgeAI] ✗ {state['error']}")
            return state

        related_sources = {}
        for affected in (plan_data.get("affected_files") or [])[:8]:
            if not isinstance(affected, dict):
                continue
            path = affected.get("path") or affected.get("file_path")
            if not isinstance(path, str) or _has_test_filename(path):
                continue
            try:
                with _workspace_path(clone_dir, path).open(encoding="utf-8") as contents:
                    related_sources[path] = contents.read(6000)
            except (OSError, ValueError):
                continue
            if len(related_sources) == 3:
                break

        failed_output = state.get("_failed_test_output", "")
        retry_context = ""
        if failed_output:
            _log(state, f"[ForgeAI] Retrying patch generation with test failure feedback (attempt {state.get('_retry_count', 1)})")
            retry_context = f"\nPrevious attempt failed. Test output (truncated):\n{failed_output[:2000]}\nFix the code so the tests pass. Do not break existing tests."

        for task in tasks:
            task_id = task.get("task_id") or task.get("id") or str(uuid.uuid4())
            file_path = task.get("file_path", "")
            if not file_path:
                _log(state, "  → Verification task deferred to the test stage")
                continue
            try:
                source_path = _workspace_path(clone_dir, file_path)
                source = "(file does not exist)"
                if source_path.is_file():
                    with source_path.open(encoding="utf-8") as contents:
                        source = contents.read(24001)
                    if len(source) > 24000:
                        source = source[:24000] + "\n[excerpt ends here]"
            except (OSError, ValueError) as exc:
                state["error"] = f"Could not read planned file {file_path}: {exc}"
                return state
            title = task.get("title", "")
            description = task.get("description", "")

            _log(state, f"  → {file_path}: {title}")

            prompt = textwrap.dedent(f"""
                You are a senior software engineer implementing a feature task.

                Feature overview: {plan_data.get('overview') or plan_data.get('summary', '')}
                Architecture notes: {plan_data.get('architecture_notes', '')}

                Task title: {title}
                Task description: {description}
                Acceptance criteria: {task.get('acceptance_criteria', '')}
                File to modify/create: {file_path}
                {retry_context}

                Current file from the base branch (source data):
                {source}

                Related checked-out source files (source data):
                {json.dumps({path: snippet for path, snippet in related_sources.items() if path != file_path})}

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

            if not diff_text:
                state["error"] = f"No patch was generated for {file_path}."
                return state
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


def apply_patches(state: BuildState) -> BuildState:
    tracer = get_tracer("forgeai.build")
    with tracer.start_as_current_span("build_run.apply_patches") as span:
        if state.get("error"):
            return state
        clone_dir = state["clone_dir"]

        # Apply each patch
        applied = 0
        for patch in state.get("generated_patches", []):
            fp = patch["file_path"]
            diff = patch.get("diff", "")
            try:
                _workspace_path(clone_dir, fp)
            except ValueError:
                state["error"] = f"Unsafe patch path: {fp!r}"
                return state

            patch_bytes = (diff.rstrip("\n") + "\n").encode()
            summary = _git("apply", "--numstat", "-z", "-", cwd=clone_dir, input=patch_bytes)
            paths = [entry.split(b"\t", 2)[-1] for entry in summary.stdout.split(b"\0") if entry]
            if summary.returncode or paths != [fp.encode()]:
                state["error"] = f"Invalid patch or unexpected target for {fp}."
                _log(state, f"[ForgeAI] ✗ {state['error']}")
                return state
            proc = _git("apply", "--index", "--whitespace=fix", "-", cwd=clone_dir, input=patch_bytes)
            if proc.returncode == 0:
                _log(state, f"  ✓ Applied patch: {fp}")
                applied += 1
            else:
                detail = proc.stderr.decode("utf-8", errors="replace").strip()
                state["error"] = f"Patch did not apply to {fp}: {detail[:400]}"
                _log(state, f"  ✗ {state['error']}")
                return state

        # Commit all written files so the workspace is clean for tests
        if applied > 0:
            _git("config", "user.email", "forgeai@local", cwd=clone_dir)
            _git("config", "user.name", "ForgeAI", cwd=clone_dir)
            committed = _git("commit", "-m", f"forgeai: apply {applied} patch(es)", cwd=clone_dir)
            if committed.returncode:
                state["error"] = "Could not commit the applied patches."
                return state

        _log(state, f"[ForgeAI] ✓ {applied}/{len(state.get('generated_patches', []))} patch(es) applied")
        span.set_attribute("applied_patches", applied)
    return state


# ── Node 3b: generate_tests ───────────────────────────────────────────────────

def _extract_test_blocks(content: str) -> list[tuple[str, str]]:
    results = []
    lines = content.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if (line.startswith("`") and line.endswith("`") and (".py" in line or ".ts" in line or ".js" in line)):
            path_candidate = line.strip("`").strip()
            j = i + 1
            while j < len(lines) and not lines[j].strip().startswith("```"):
                j += 1
            if j < len(lines):
                code_lines = []
                k = j + 1
                while k < len(lines) and not lines[k].strip().startswith("```"):
                    code_lines.append(lines[k])
                    k += 1
                if code_lines and path_candidate:
                    results.append((path_candidate, "\n".join(code_lines)))
                i = k + 1
                continue
        i += 1
    return results


def generate_tests(state: BuildState) -> BuildState:
    """
    Call testing_agent to generate tests for every file touched in this build,
    write them into the clone_dir, and commit them alongside the feature patches.
    """
    if state.get("error"):
        return state
    tracer = get_tracer("forgeai.build")
    with tracer.start_as_current_span("build_run.generate_tests") as span:
        from app.services.testing_agent import run_testing_agent, TargetNotFound

        _log(state, "[ForgeAI] Generating tests for patched files…")
        clone_dir = state.get("clone_dir", "")
        patches = state.get("generated_patches", [])
        generated_test_files: list[dict] = []

        # Build a lookup: file_path → code extracted from the diff's added lines.
        # Used as fallback when a file is newly created and not yet indexed in Qdrant.
        patch_content_map: dict[str, str] = {}
        for _patch in patches:
            fp_key = _patch.get("file_path", "")
            diff_text = _patch.get("diff", "")
            if fp_key and diff_text:
                plus_lines = [
                    line[1:] for line in diff_text.splitlines()
                    if line.startswith("+") and not line.startswith("+++")
                ]
                if plus_lines:
                    patch_content_map[fp_key] = "\n".join(plus_lines)

        for patch in patches:
            fp = patch.get("file_path", "")
            if not fp or os.path.basename(fp) == "conftest.py" or _has_test_filename(fp):
                continue

            try:
                result = run_testing_agent(
                    org_id=state["org_id"],
                    repository_id=state["repository_id"],
                    repository_name=state.get("repo_full_name", ""),
                    file_path=fp,
                    patch_content=patch_content_map.get(fp),
                )
                test_blocks = _extract_test_blocks(result.content)
                for test_path, test_code in test_blocks:
                    abs_test = _workspace_path(clone_dir, test_path)
                    if not _has_test_filename(test_path) or abs_test.exists():
                        continue
                    abs_test.parent.mkdir(parents=True, exist_ok=True)
                    abs_test.write_text(test_code, encoding="utf-8")
                    _git("add", test_path, cwd=clone_dir)
                    generated_test_files.append({"file_path": test_path})
                    _log(state, f"  ✓ Generated test: {test_path}")
            except TargetNotFound:
                _log(state, f"  ⚠ No content available for {fp} — skipping test gen")
            except Exception as exc:
                _log(state, f"  ⚠ Test generation failed for {fp}: {exc}")

        if generated_test_files:
            _git("config", "user.email", "forgeai@forgeai.local", cwd=clone_dir)
            _git("config", "user.name", "ForgeAI", cwd=clone_dir)
            _git("commit", "-m", f"forgeai: add generated tests for {len(generated_test_files)} file(s)", cwd=clone_dir)
            _log(state, f"[ForgeAI] ✓ {len(generated_test_files)} test file(s) committed")
        else:
            _log(state, "[ForgeAI] ⚠ No test files generated — continuing")

        state["_generated_test_files"] = generated_test_files
        span.set_attribute("generated_tests_count", len(generated_test_files))
    return state


# ── Node 4: spin_up_sandbox ───────────────────────────────────────────────────

def spin_up_sandbox(state: BuildState) -> BuildState:
    if state.get("error"):
        return state
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
                _log(state, "[ForgeAI] ⚠ Docker daemon not responding — isolated runner unavailable")
                state["_docker_available"] = False  # type: ignore[typeddict-unknown-key]
        except FileNotFoundError:
            _log(state, "[ForgeAI] ⚠ Docker CLI not found — isolated runner unavailable")
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
def _has_test_filename(path: str) -> bool:
    name = os.path.basename(path)
    return (
        (name.endswith(".py") and (name.startswith("test_") or name.endswith("_test.py")))
        or bool(re.search(r"\.(test|spec)\.[jt]sx?$", name))
    )


def _has_python_tests(directory: str) -> bool:
    """Return True if the directory contains any pytest-discoverable test files."""
    for root, _, files in os.walk(directory):
        for fname in files:
            if fname.startswith("test_") and fname.endswith(".py"):
                return True
            if fname.endswith("_test.py"):
                return True
    return False


def _has_js_tests(directory: str) -> bool:
    """Return True if the directory contains any JS/TS test files."""
    for root, _, files in os.walk(directory):
        for fname in files:
            if fname.endswith(
                (
                    ".test.js",
                    ".test.ts",
                    ".spec.js",
                    ".spec.ts",
                    ".test.jsx",
                    ".test.tsx",
                    ".spec.jsx",
                    ".spec.tsx",
                )
            ):
                return True
    return False


def _detect_js_test_runner(directory: str) -> str | None:
    pkg_path = os.path.join(directory, "package.json")
    if not os.path.isfile(pkg_path):
        return None
    try:
        with open(pkg_path, encoding="utf-8") as fh:
            pkg = json.load(fh)
        scripts = pkg.get("scripts", {})
        test_cmd = scripts.get("test", "")
        deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
        if "vitest" in deps or "vitest" in test_cmd:
            return "vitest"
        if "jest" in deps or "jest" in test_cmd:
            return "jest"
    except Exception:
        pass
    return None


_ENV_PATTERNS = [
    re.compile(r"KeyError:\s*['\"]([A-Z_][A-Z0-9_]+)['\"]"),
    re.compile(r"(?i:missing|not set|required|environment variable).*?\b([A-Z_][A-Z0-9_]{2,})\b"),
    re.compile(r"os\.environ\[['\"]([A-Z_][A-Z0-9_]+)['\"]]"),
]


def _detect_missing_env_vars(raw_output: str) -> list[str]:
    found = set()
    for pattern in _ENV_PATTERNS:
        for m in pattern.finditer(raw_output):
            candidate = m.group(1)
            if len(candidate) >= 3:
                found.add(candidate)
    return sorted(found)


def _parse_text_results(raw: str, results: dict) -> None:
    """Extract passed/failed counts from test plain-text output."""
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
        network_mode = state.get("_network_mode", "none")

        env_flags: list[str] = []
        for k, v in (state.get("env_vars") or {}).items():
            env_flags.extend(["-e", f"{k}={v}"])

        test_results: dict = {
            "passed": 0, "failed": 0, "errors": 0,
            "duration": 0.0, "exit_code": 0, "suites": [], "raw_output": "",
        }

        # ── 1. Language detection ─────────────────────────────────────────────
        has_py = _has_python_tests(clone_dir) if clone_dir else False
        has_js = _has_js_tests(clone_dir) if clone_dir else False

        blocked = state.get("error")
        if not blocked and not has_py and not has_js:
            blocked = "No Python or JS test files found in the checkout."
        if not blocked and not docker_available:
            blocked = "No isolated test runner is available. Configure the runner before retrying."
        if not blocked and has_py and network_mode == "none" and not settings.BUILD_PYTHON_TEST_IMAGE:
            blocked = "Offline Python testing requires a prepared BUILD_PYTHON_TEST_IMAGE with the project dependencies."
        if blocked:
            test_results["exit_code"] = -1
            test_results["raw_output"] = blocked
            state["test_results"] = test_results
            state["error"] = blocked
            _log(state, f"[ForgeAI] ✗ {blocked}")
            return state

        # ── 2. JS / TS test runner (if project has JS tests) ───────────────────
        if has_js and docker_available and clone_dir:
            js_runner = _detect_js_test_runner(clone_dir) or "jest"
            _log(state, f"[ForgeAI] Running {js_runner} tests in isolated container (node:20-slim)…")
            try:
                install_cmd = "npm ci --prefer-offline 2>/dev/null || npm install -q"
                test_cmd = f"npx {js_runner} --reporter=json 2>/dev/null || npx {js_runner}"
                proc = subprocess.run(
                    [
                        "docker", "run", "--rm",
                        "--network", network_mode,
                        *env_flags,
                        "-v", f"{clone_dir}:/workspace:ro",
                        "-w", "/workspace",
                        "node:20-slim",
                        "bash", "-c",
                        f"mkdir -p /tmp/project && cp -a /workspace/. /tmp/project/ && "
                        f"cd /tmp/project && {install_cmd} && {test_cmd}",
                    ],
                    capture_output=True, timeout=300,
                )
                raw_js = (proc.stdout + proc.stderr).decode("utf-8", errors="replace")
                test_results["raw_output"] += f"\n--- JS/TS ({js_runner}) ---\n{raw_js[-3000:]}"
                if proc.returncode != 0:
                    test_results["exit_code"] = proc.returncode
                try:
                    js_report = json.loads(raw_js.strip().splitlines()[-1])
                    test_results["passed"] += js_report.get("numPassedTests", 0)
                    test_results["failed"] += js_report.get("numFailedTests", 0)
                except Exception:
                    _parse_text_results(raw_js, test_results)
                _log(state, f"[ForgeAI] JS test exit={proc.returncode}")
            except Exception as exc:
                test_results["exit_code"] = -1
                test_results["raw_output"] += f"\nJS test runner error: {exc}"
                _log(state, f"[ForgeAI] ✗ JS test runner error: {exc}")

        # ── 3. Python Docker runner ────────────────────────────────────────────
        if has_py and docker_available and clone_dir:
            image = settings.BUILD_PYTHON_TEST_IMAGE or "python:3.11-slim"
            setup = ""
            if not settings.BUILD_PYTHON_TEST_IMAGE:
                setup = (
                    "python -m pip install -q pytest pytest-json-report; "
                    "if [ -f requirements.txt ]; then python -m pip install -q -r requirements.txt; fi; "
                )
            _log(state, f"[ForgeAI] Launching isolated test container ({image})…")
            try:
                proc = subprocess.run(
                    [
                        "docker", "run", "--rm",
                        "--network", network_mode,
                        *env_flags,
                        "-v", f"{clone_dir}:/workspace:ro",
                        "-w", "/workspace",
                        image,
                        "bash", "-c",
                        (
                            f"set -e; {setup}"
                            "exit_code=0; "
                            "python -m pytest --json-report --json-report-file=/tmp/report.json "
                            "--tb=short -q . || exit_code=$?; "
                            "if [ -f /tmp/report.json ]; then echo '---JSON---'; cat /tmp/report.json; fi; "
                            "exit \"$exit_code\""
                        ),
                    ],
                    capture_output=True, timeout=300,
                )
                raw = (proc.stdout + proc.stderr).decode("utf-8", errors="replace")
                if proc.returncode:
                    test_results["exit_code"] = proc.returncode
                test_results["raw_output"] += f"\n{raw[-6000:]}"

                try:
                    marker = raw.rfind("---JSON---")
                    blob = raw[marker + 10:].strip() if marker >= 0 else "{}"
                    report, _ = json.JSONDecoder().raw_decode(blob)
                    summary = report.get("summary", {})
                    test_results["passed"] += summary.get("passed", 0)
                    test_results["failed"] += summary.get("failed", 0)
                    test_results["errors"] += summary.get("error", 0)
                    test_results["duration"] = round(report.get("duration", 0.0), 2)
                except Exception:
                    _parse_text_results(raw, test_results)

            except subprocess.TimeoutExpired:
                test_results["exit_code"] = -1
                test_results["raw_output"] += "\nTest run timed out after 300s"
                _log(state, "[ForgeAI] ✗ Tests timed out")
            except Exception as exc:
                test_results["exit_code"] = -1
                test_results["raw_output"] += f"\n{exc}"
                _log(state, f"[ForgeAI] ✗ Docker test runner error: {exc}")

        # ── 6. HITL: Pause if tests failed due to missing env vars ─────────────
        if test_results["exit_code"] != 0 and interrupt is not None:
            missing_vars = _detect_missing_env_vars(test_results.get("raw_output", ""))
            if missing_vars:
                _log(state, f"[ForgeAI] ⏸ Env vars may be missing: {missing_vars}")
                interrupt_data = {
                    "type": "env_vars_needed",
                    "missing_vars": missing_vars,
                    "build_run_id": state["build_run_id"],
                    "message": f"Tests may need env vars: {missing_vars}",
                }
                with db_session() as db:
                    run_row = db.query(BuildRun).filter(BuildRun.id == state["build_run_id"]).first()
                    if run_row:
                        run_row.interrupt_payload = interrupt_data
                _set_status(state["build_run_id"], "waiting_for_input")
                try:
                    human_input: dict = interrupt(interrupt_data)
                    provided_vars: dict = human_input.get("vars", {})
                    if provided_vars:
                        merged = {**(state.get("env_vars") or {}), **provided_vars}
                        state["env_vars"] = merged
                        with db_session() as db:
                            run_row = db.query(BuildRun).filter(BuildRun.id == state["build_run_id"]).first()
                            if run_row:
                                run_row.env_vars = merged
                        _set_status(state["build_run_id"], "integration_testing")
                        _log(state, f"[ForgeAI] ✓ Received {len(provided_vars)} env var(s) — retrying tests")
                        state["test_results"] = None
                        state["_failed_test_output"] = ""
                        state["_retry_count"] = max(0, state.get("_retry_count", 1) - 1)
                        return state
                except Exception as hitl_exc:
                    _log(state, f"[ForgeAI] ⚠ HITL interrupt error: {hitl_exc}")

        # ── 7. Record failure for retry loop ───────────────────────────────────
        if test_results["exit_code"] != 0 or test_results["failed"] > 0 or test_results["errors"] > 0:
            raw_out = test_results.get("raw_output", "")
            state["_failed_test_output"] = raw_out[-3000:] if raw_out else ""
            state["_retry_count"] = state.get("_retry_count", 0) + 1
            _log(state, f"[ForgeAI] Tests failed — attempt {state['_retry_count']}/{MAX_PATCH_RETRIES + 1}")

        status_icon = "✓" if not any(test_results[key] for key in ("exit_code", "failed", "errors")) else "✗"
        _log(
            state,
            f"[ForgeAI] {status_icon} Tests complete — "
            f"passed={test_results['passed']}  failed={test_results['failed']}  "
            f"errors={test_results['errors']}  exit={test_results['exit_code']}",
        )
        state["test_results"] = test_results
        span.set_attribute("tests.passed", test_results["passed"])
        span.set_attribute("tests.failed", test_results["failed"])
        span.set_attribute("tests.exit_code", test_results["exit_code"])

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
            state["error"] = state.get("error") or (
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

        if error or exit_code != 0 or failed > 0 or test_results.get("errors", 0) > 0:
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
    """
    After run_tests:
      - pass                   → open_pr
      - fail + retries remain  → generate_patches (loop back with failure feedback)
      - fail + retries over    → open_pr (open_pr will detect failed tests and stop)
    """
    if state.get("error"):
        return "open_pr"

    test_results = state.get("test_results") or {}
    exit_code = test_results.get("exit_code", -1)
    failed = test_results.get("failed", 0)
    errors = test_results.get("errors", 0)
    retry_count = state.get("_retry_count", 0)

    tests_passed = (exit_code == 0 and failed == 0 and errors == 0)
    if tests_passed:
        return "open_pr"

    if retry_count <= MAX_PATCH_RETRIES:
        return "generate_patches"

    return "open_pr"


# ── Graph assembly ────────────────────────────────────────────────────────────

def _build_graph():
    g = StateGraph(BuildState)
    g.add_node("init_run", init_run)
    g.add_node("generate_patches", generate_patches)
    g.add_node("apply_patches", apply_patches)
    g.add_node("generate_tests", generate_tests)
    g.add_node("spin_up_sandbox", spin_up_sandbox)
    g.add_node("run_tests", run_tests)
    g.add_node("open_pr", open_pr)
    g.add_node("finalise", finalise)

    g.set_entry_point("init_run")
    g.add_edge("init_run", "generate_patches")
    g.add_edge("generate_patches", "apply_patches")
    g.add_edge("apply_patches", "generate_tests")
    g.add_edge("generate_tests", "spin_up_sandbox")
    g.add_edge("spin_up_sandbox", "run_tests")

    g.add_conditional_edges(
        "run_tests",
        _should_continue_after_tests,
        {"open_pr": "open_pr", "generate_patches": "generate_patches"},
    )
    g.add_edge("open_pr", "finalise")
    g.add_edge("finalise", END)

    # Use InMemorySaver for HITL interrupt support.
    # PostgresSaver.from_conn_string() returns a context manager, not a saver
    # instance directly — using it requires `with` block management which
    # doesn't fit the module-level singleton pattern here.  InMemorySaver is
    # sufficient: interrupts persist across resume() calls within the same
    # process lifetime, which covers the HITL env-var flow.
    try:
        from langgraph.checkpoint.memory import InMemorySaver
        checkpointer = InMemorySaver()
        logger.info("Build graph: using InMemorySaver checkpointer")
    except ImportError:
        try:
            from langgraph.checkpoint.memory import MemorySaver
            checkpointer = MemorySaver()
            logger.info("Build graph: using MemorySaver checkpointer (fallback)")
        except Exception:
            checkpointer = None
            logger.warning("Build graph: no checkpointer available — HITL interrupt disabled")

    return g.compile(checkpointer=checkpointer) if checkpointer else g.compile()


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
        config = {"configurable": {"thread_id": build_run_id}}
        final_state = graph.invoke(initial_state, config=config)
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


def resume_build_execution(build_run_id: str, human_input: dict) -> None:
    """
    Resume a paused (interrupted) build graph by supplying human input.
    Called from the /resume endpoint in a background thread.
    """
    try:
        graph = _get_graph()
        config = {"configurable": {"thread_id": build_run_id}}
        if Command is not None:
            graph.invoke(Command(resume=human_input), config=config)
        else:
            logger.warning("Command not available to resume LangGraph execution")
    except Exception as exc:
        logger.exception("Failed to resume build execution: %s", exc)
        try:
            _set_status(
                build_run_id,
                "failed",
                error_message=f"Resume failed: {exc}",
                completed_at=datetime.now(timezone.utc),
            )
            _append_log(build_run_id, [f"[ForgeAI] ✗ Resume failed: {exc}"])
        except Exception:
            pass
