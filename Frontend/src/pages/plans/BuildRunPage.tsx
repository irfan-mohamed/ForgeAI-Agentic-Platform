/**
 * BuildRunPage — Live build execution viewer for Phase 4.
 *
 * Split-panel layout:
 *   Left  (1/3): Plan metadata + generated file patches
 *   Right (2/3): Live terminal log stream + test results + PR card
 */
import { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { PageLayout, PageHeader } from '@/components/layout/PageLayout';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Spinner } from '@/components/ui/Spinner';
import { buildRunsApi } from '@/api/buildRuns';
import type { BuildRunOut, BuildRunStatus, Patch, TestResults } from '@/types';

const TERMINAL_STATUSES: BuildRunStatus[] = ['pr_opened', 'failed'];

function StatusBadge({ status }: { status: BuildRunStatus }) {
  const cfg: Record<BuildRunStatus, { label: string; cls: string; pulse: boolean }> = {
    queued:              { label: 'Queued',              cls: 'bg-surface-700/60 text-surface-300 border-white/10',                       pulse: false },
    building:            { label: 'Building',            cls: 'bg-blue-500/20 text-blue-300 border-blue-500/40',                           pulse: true  },
    integration_testing: { label: 'Integration Testing', cls: 'bg-purple-500/20 text-purple-300 border-purple-500/40',                     pulse: true  },
    pr_opened:           { label: 'PR Opened',           cls: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40',                  pulse: false },
    failed:              { label: 'Failed',              cls: 'bg-red-500/20 text-red-300 border-red-500/40',                             pulse: false },
  };
  const { label, cls, pulse } = cfg[status] ?? cfg.queued;
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-mono font-semibold uppercase tracking-widest border ${cls} ${
        pulse ? 'animate-pulse' : ''
      }`}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${
        status === 'pr_opened' ? 'bg-emerald-400' :
        status === 'failed'    ? 'bg-red-400' :
        status === 'queued'    ? 'bg-surface-400' :
        'bg-current'
      }`} />
      {label}
    </span>
  );
}

function LogLine({ line }: { line: string }) {
  const isSuccess = line.includes('✓') || line.startsWith('[ForgeAI');
  const isError   = line.includes('✗') || line.toLowerCase().includes('error') || line.toLowerCase().includes('failed');
  const isWarn    = line.includes('⚠') || line.toLowerCase().includes('warning');
  const cls = isError ? 'text-red-400' : isWarn ? 'text-amber-400' : isSuccess ? 'text-emerald-400' : 'text-surface-300';
  return <div className={`font-mono text-[11px] leading-relaxed whitespace-pre-wrap break-all ${cls}`}>{line}</div>;
}

function PatchViewer({ patches }: { patches: Patch[] }) {
  const [open, setOpen] = useState<string | null>(null);

  if (!patches.length) return null;

  return (
    <div className="space-y-2">
      <h4 className="text-xs font-bold text-white uppercase tracking-wider">
        Generated Patches ({patches.length})
      </h4>
      {patches.map((p, idx) => {
        const key = p.task_id || `patch-${idx}`;
        const isOpen = open === key;
        return (
          <div key={key} className="border border-white/8 rounded-xl overflow-hidden">
            <button
              onClick={() => setOpen(isOpen ? null : key)}
              className="w-full flex items-center justify-between p-3 text-left hover:bg-white/5 transition-colors"
            >
              <span className="font-mono text-[11px] text-forge-300 truncate">{p.file_path}</span>
              <span className="text-[10px] text-surface-500 ml-2">
                {isOpen ? '▲' : '▼'}
              </span>
            </button>
            {isOpen && p.diff && (
              <pre className="text-[10px] font-mono overflow-x-auto p-3 bg-black/40 border-t border-white/8 leading-relaxed">
                {p.diff.split('\n').map((line, i) => (
                  <div
                    key={i}
                    className={`${
                      line.startsWith('+') && !line.startsWith('+++') ? 'text-emerald-400' :
                      line.startsWith('-') && !line.startsWith('---') ? 'text-red-400' :
                      line.startsWith('@@') ? 'text-blue-400' :
                      'text-surface-400'
                    }`}
                  >
                    {line}
                  </div>
                ))}
              </pre>
            )}
            {isOpen && !p.diff && (
              <p className="text-[11px] text-surface-500 p-3 border-t border-white/8">No diff available</p>
            )}
          </div>
        );
      })}
    </div>
  );
}

function TestResultsCard({ results }: { results: TestResults }) {
  const [showRaw, setShowRaw] = useState(false);
  const allPassed = (results.failed ?? 0) === 0 && (results.errors ?? 0) === 0;

  return (
    <div className={`p-4 rounded-2xl border ${
      allPassed
        ? 'bg-emerald-500/10 border-emerald-500/30'
        : 'bg-red-500/10 border-red-500/30'
    }`}>
      <div className="flex items-center justify-between mb-3">
        <h4 className="text-xs font-bold text-white uppercase tracking-wider">Test Results</h4>
        <span className="text-[11px] text-surface-400">{(results.duration ?? 0).toFixed(1)}s</span>
      </div>
      <div className="flex items-center gap-4 mb-3">
        <div className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-emerald-400" />
          <span className="text-sm font-bold text-emerald-300">{results.passed ?? 0}</span>
          <span className="text-xs text-surface-400">passed</span>
        </div>
        {(results.failed ?? 0) > 0 && (
          <div className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-red-400" />
            <span className="text-sm font-bold text-red-300">{results.failed}</span>
            <span className="text-xs text-surface-400">failed</span>
          </div>
        )}
        {(results.errors ?? 0) > 0 && (
          <div className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-amber-400" />
            <span className="text-sm font-bold text-amber-300">{results.errors}</span>
            <span className="text-xs text-surface-400">errors</span>
          </div>
        )}
      </div>
      {results.raw_output && (
        <>
          <button
            onClick={() => setShowRaw(!showRaw)}
            className="text-[11px] text-surface-400 hover:text-white transition-colors underline underline-offset-2"
          >
            {showRaw ? 'Hide' : 'Show'} raw output
          </button>
          {showRaw && (
            <pre className="mt-2 text-[10px] font-mono text-surface-300 bg-black/40 p-3 rounded-xl overflow-auto max-h-60 border border-white/8">
              {results.raw_output}
            </pre>
          )}
        </>
      )}
    </div>
  );
}

export function BuildRunPage() {
  const { orgId: orgIdStr, buildRunId } = useParams<{ orgId: string; buildRunId: string }>();
  const navigate = useNavigate();
  const orgId = Number(orgIdStr);

  const [buildRun, setBuildRun]       = useState<BuildRunOut | null>(null);
  const [logLines, setLogLines]       = useState<string[]>([]);
  const [loading, setLoading]         = useState(true);
  const [error, setError]             = useState('');
  const terminalRef                   = useRef<HTMLDivElement>(null);
  const sseRef                        = useRef<EventSource | null>(null);
  const pollRef                       = useRef<ReturnType<typeof setInterval> | null>(null);
  const isTerminal                    = useRef(false);
  // Guard: only open ONE SSE connection per buildRunId (prevents duplicate log lines
  // caused by React StrictMode double-mount or status-change dep re-runs).
  const sseConnected                  = useRef(false);

  const scrollToBottom = useCallback(() => {
    if (terminalRef.current) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
    }
  }, []);

  // Load initial build run data
  useEffect(() => {
    if (!buildRunId) return;
    buildRunsApi.getBuildRun(buildRunId)
      .then((res) => {
        setBuildRun(res.data);
        if (res.data.build_log) {
          setLogLines(res.data.build_log.split('\n').filter(Boolean));
        }
        if (TERMINAL_STATUSES.includes(res.data.status)) {
          isTerminal.current = true;
        }
      })
      .catch(() => setError('Failed to load build run.'))
      .finally(() => setLoading(false));
  }, [buildRunId]);

  // Connect to SSE stream — runs once per buildRunId, never re-runs on status change.
  useEffect(() => {
    if (!buildRunId || !buildRun) return;
    if (TERMINAL_STATUSES.includes(buildRun.status)) {
      isTerminal.current = true;
      return;
    }
    // Guard against double-mount (React StrictMode) and status-change re-runs
    if (sseConnected.current) return;
    sseConnected.current = true;

    const es = buildRunsApi.createLogStream(buildRunId);
    sseRef.current = es;

    es.addEventListener('log', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data);
        setLogLines((prev) => [...prev, data.line]);
      } catch {
        setLogLines((prev) => [...prev, e.data]);
      }
      setTimeout(scrollToBottom, 50);
    });

    es.addEventListener('status', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data);
        setBuildRun((prev) => prev ? { ...prev, status: data.status } : prev);
      } catch {
        // ignore
      }
    });

    es.addEventListener('complete', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data);
        setBuildRun((prev) => prev ? { ...prev, ...data } : prev);
      } catch {
        // ignore
      }
      isTerminal.current = true;
      es.close();
      sseConnected.current = false;
    });

    es.addEventListener('error', (e: Event) => {
      try {
        const me = e as MessageEvent;
        if (me.data) {
          const data = JSON.parse(me.data);
          setBuildRun((prev) => prev ? { ...prev, ...data } : prev);
          if (data.status && TERMINAL_STATUSES.includes(data.status)) {
            isTerminal.current = true;
          }
        }
      } catch {
        // SSE connection error — let polling take over
      }
      es.close();
      sseConnected.current = false;
    });

    return () => {
      es.close();
      sseRef.current = null;
      sseConnected.current = false;
    };
  // Only connect once when the initial buildRun data loads — NOT on status changes.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [buildRunId, buildRun !== null, scrollToBottom]);

  // Fallback polling every 3s
  useEffect(() => {
    if (!buildRunId) return;

    const poll = setInterval(async () => {
      if (isTerminal.current) {
        clearInterval(poll);
        return;
      }
      try {
        const res = await buildRunsApi.getBuildRun(buildRunId);
        setBuildRun(res.data);
        if (res.data.build_log) {
          setLogLines((prev) => {
            const serverLines = res.data.build_log?.split('\n').filter(Boolean) ?? [];
            return serverLines.length > prev.length ? serverLines : prev;
          });
          setTimeout(scrollToBottom, 50);
        }
        if (TERMINAL_STATUSES.includes(res.data.status)) {
          isTerminal.current = true;
          clearInterval(poll);
        }
      } catch {
        // ignore poll errors
      }
    }, 3000);

    pollRef.current = poll;
    return () => clearInterval(poll);
  }, [buildRunId, scrollToBottom]);

  if (loading) {
    return (
      <PageLayout>
        <div className="flex items-center justify-center min-h-[400px]">
          <Spinner size="lg" />
        </div>
      </PageLayout>
    );
  }

  if (error || !buildRun) {
    return (
      <PageLayout>
        <div className="text-center py-20">
          <p className="text-red-400 text-sm">{error || 'Build run not found.'}</p>
          <Button variant="secondary" size="sm" className="mt-4" onClick={() => navigate(-1)}>
            ← Go Back
          </Button>
        </div>
      </PageLayout>
    );
  }

  const isActive = !TERMINAL_STATUSES.includes(buildRun.status);
  const patches = buildRun.generated_patches ?? [];
  const tr = buildRun.test_results;

  return (
    <PageLayout>
      <PageHeader
        title="Build Execution"
        subtitle="AI-generated implementation · Integration test suite · Auto-PR"
        action={
          <div className="flex items-center gap-3">
            <StatusBadge status={buildRun.status} />
            <Button
              variant="secondary"
              size="sm"
              onClick={() => navigate(`/organizations/${orgId}/plans`)}
            >
              ← Feature Plans
            </Button>
          </div>
        }
      />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left panel: Metadata + Patches */}
        <div className="lg:col-span-1 space-y-4">
          {/* Build Run Info */}
          <Card>
            <h3 className="text-xs font-bold text-white uppercase tracking-wider mb-4">
              Build Info
            </h3>
            <div className="space-y-3">
              <div>
                <p className="text-[10px] text-surface-500 uppercase tracking-wider">Build Run ID</p>
                <p className="font-mono text-xs text-surface-300 mt-0.5 truncate">{buildRun.id.slice(0, 16)}…</p>
              </div>
              <div>
                <p className="text-[10px] text-surface-500 uppercase tracking-wider">Branch</p>
                <p className="font-mono text-xs text-forge-300 mt-0.5">{buildRun.branch_name ?? '—'}</p>
              </div>
              {buildRun.otel_trace_id && (
                <div>
                  <p className="text-[10px] text-surface-500 uppercase tracking-wider">Trace ID</p>
                  <p className="font-mono text-[10px] text-purple-300 mt-0.5 truncate">
                    {buildRun.otel_trace_id.slice(0, 16)}…
                  </p>
                </div>
              )}
              {buildRun.started_at && (
                <div>
                  <p className="text-[10px] text-surface-500 uppercase tracking-wider">Started</p>
                  <p className="text-xs text-surface-300 mt-0.5">
                    {new Date(buildRun.started_at).toLocaleTimeString()}
                  </p>
                </div>
              )}
              {buildRun.completed_at && (
                <div>
                  <p className="text-[10px] text-surface-500 uppercase tracking-wider">Completed</p>
                  <p className="text-xs text-surface-300 mt-0.5">
                    {new Date(buildRun.completed_at).toLocaleTimeString()}
                  </p>
                </div>
              )}
            </div>
          </Card>

          {/* Generated Patches */}
          {patches.length > 0 && (
            <Card>
              <PatchViewer patches={patches} />
            </Card>
          )}
        </div>

        {/* Right panel: Terminal + Results */}
        <div className="lg:col-span-2 space-y-4">
          {/* Terminal */}
          <Card className="flex flex-col">
            <div className="flex items-center justify-between pb-3 mb-3 border-b border-white/8">
              <div className="flex items-center gap-2">
                <div className="flex gap-1">
                  <span className="w-2.5 h-2.5 rounded-full bg-red-500/70" />
                  <span className="w-2.5 h-2.5 rounded-full bg-amber-500/70" />
                  <span className="w-2.5 h-2.5 rounded-full bg-emerald-500/70" />
                </div>
                <span className="text-xs font-mono text-surface-400">forge-build-agent</span>
              </div>
              {isActive && (
                <div className="flex items-center gap-1.5">
                  <Spinner size="sm" />
                  <span className="text-[10px] text-surface-400">
                    {buildRun.status === 'integration_testing' ? 'Running integration tests...' : 'Building...'}
                  </span>
                </div>
              )}
            </div>

            <div
              ref={terminalRef}
              className="bg-black/60 rounded-xl p-4 h-80 overflow-y-auto space-y-0.5 font-mono"
            >
              {logLines.length === 0 ? (
                <div className="text-surface-500 text-[11px] font-mono">
                  Waiting for build to start...
                </div>
              ) : (
                logLines.map((line, i) => <LogLine key={i} line={line} />)
              )}
              {isActive && (
                <div className="text-forge-400 font-mono text-[11px] mt-1 animate-pulse">▌</div>
              )}
            </div>
          </Card>

          {/* Test Results */}
          {tr && <TestResultsCard results={tr} />}

          {/* PR Card (success) */}
          {buildRun.status === 'pr_opened' && buildRun.pull_request_url && (
            <Card className="border-emerald-500/30 bg-emerald-500/5">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-emerald-500/20 flex items-center justify-center">
                    <svg className="w-5 h-5 text-emerald-400" fill="currentColor" viewBox="0 0 24 24">
                      <path d="M18 6L7 17l-5-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" fill="none"/>
                    </svg>
                  </div>
                  <div>
                    <h4 className="text-sm font-semibold text-white">Pull Request Opened</h4>
                    <p className="text-xs text-emerald-300 mt-0.5">
                      #{buildRun.pull_request_number} · All integration tests passed
                    </p>
                  </div>
                </div>
                <a
                  href={buildRun.pull_request_url}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <Button variant="primary" size="sm">
                    View PR on GitHub ↗
                  </Button>
                </a>
              </div>
            </Card>
          )}

          {/* PR opened but no URL (no GitHub token) */}
          {buildRun.status === 'pr_opened' && !buildRun.pull_request_url && (
            <Card className="border-emerald-500/30 bg-emerald-500/5">
              <p className="text-sm font-semibold text-emerald-300">✓ All tests passed</p>
              <p className="text-xs text-surface-400 mt-1">
                No GitHub token configured — PR was not auto-opened. Review generated patches above.
              </p>
            </Card>
          )}

          {/* Error Card (failure) */}
          {buildRun.status === 'failed' && (
            <Card className="border-red-500/30 bg-red-500/5">
              <div className="flex items-start gap-3">
                <div className="w-10 h-10 rounded-xl bg-red-500/20 flex items-center justify-center shrink-0">
                  <svg className="w-5 h-5 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </div>
                <div>
                  <h4 className="text-sm font-semibold text-red-300">Build Failed</h4>
                  {buildRun.error_message && (
                    <p className="text-xs text-surface-400 mt-1 font-mono">{buildRun.error_message}</p>
                  )}
                </div>
              </div>
            </Card>
          )}
        </div>
      </div>
    </PageLayout>
  );
}
