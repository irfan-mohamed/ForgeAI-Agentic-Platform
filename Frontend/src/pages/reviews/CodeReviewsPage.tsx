/**
 * CodeReviewsPage — list of PR code reviews and trigger new AI review.
 */
import { useEffect, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { PageLayout, PageHeader } from '@/components/layout/PageLayout';
import { reviewsApi } from '@/api/reviews';
import { repositoryApi } from '@/api/repository';
import { pullRequestsApi } from '@/api/pullRequests';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { SeverityBadge } from '@/components/ui/Badge';
import { Spinner } from '@/components/ui/Spinner';
import type {
  CodeReviewSummary,
  Repository,
  PullRequestSummary,
} from '@/types';

// ── Trigger Review Modal ───────────────────────────────────────────────────────

interface StartReviewModalProps {
  repos: Repository[];
  orgId: number;
  onClose: () => void;
  onStarted: (review: CodeReviewSummary) => void;
}

function StartReviewModal({ repos, orgId, onClose, onStarted }: StartReviewModalProps) {
  const [selectedRepoId, setSelectedRepoId] = useState<number | null>(null);
  const [pullRequests, setPullRequests]     = useState<PullRequestSummary[]>([]);
  const [loadingPRs, setLoadingPRs]         = useState(false);
  const [selectedPRNumber, setSelectedPRNumber] = useState<number | null>(null);
  const [submitting, setSubmitting]         = useState(false);
  const [error, setError]                   = useState('');

  const readyRepos = repos.filter(r => r.status === 'ready');

  // Fetch pull requests when repo selected
  useEffect(() => {
    if (!selectedRepoId) {
      setPullRequests([]);
      return;
    }
    setLoadingPRs(true);
    setError('');
    pullRequestsApi.list(selectedRepoId, { state: 'open' })
      .then((res) => {
        setPullRequests(res.data.pull_requests || []);
      })
      .catch(() => {
        setError('Failed to fetch open pull requests for this repository.');
      })
      .finally(() => setLoadingPRs(false));
  }, [selectedRepoId]);

  const handleStartReview = async () => {
    if (!selectedRepoId || !selectedPRNumber) {
      setError('Please select both a repository and a pull request.');
      return;
    }

    setSubmitting(true);
    setError('');
    try {
      const res = await reviewsApi.startReview(orgId, {
        repository_id: selectedRepoId,
        pull_number: selectedPRNumber,
      });
      onStarted(res.data);
      onClose();
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(typeof msg === 'string' ? msg : 'Failed to start review.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-fade-in">
      <div className="w-full max-w-lg glass-card p-6 border border-white/10 shadow-2xl animate-slide-up space-y-5">
        <div className="flex items-center justify-between pb-3 border-b border-white/8">
          <div>
            <h3 className="text-base font-bold text-white">Start AI Code Review</h3>
            <p className="text-xs text-surface-400 mt-0.5">Select a pull request from an indexed repository</p>
          </div>
          <button onClick={onClose} className="text-surface-400 hover:text-white transition-colors">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Step 1: Select Repo */}
        <div>
          <label className="block text-xs font-medium text-surface-300 mb-1.5">
            Target Repository <span className="text-red-400">*</span>
          </label>
          <select
            value={selectedRepoId ?? ''}
            onChange={(e) => {
              setSelectedRepoId(Number(e.target.value) || null);
              setSelectedPRNumber(null);
            }}
            className="w-full bg-surface-900 border border-white/10 rounded-xl px-3 py-2.5 text-xs text-white focus:outline-none focus:ring-2 focus:ring-forge-500/40"
          >
            <option value="">Select a ready repository…</option>
            {readyRepos.map((r) => (
              <option key={r.id} value={r.id} className="bg-surface-900 text-white">
                {r.full_name}
              </option>
            ))}
          </select>
        </div>

        {/* Step 2: Select PR */}
        {selectedRepoId && (
          <div>
            <label className="block text-xs font-medium text-surface-300 mb-1.5">
              Select Open Pull Request <span className="text-red-400">*</span>
            </label>
            {loadingPRs ? (
              <div className="flex justify-center py-4"><Spinner size="sm" /></div>
            ) : pullRequests.length === 0 ? (
              <div className="p-4 bg-surface-900/60 rounded-xl border border-white/5 text-center text-xs text-surface-400">
                No open pull requests found for this repository.
              </div>
            ) : (
              <div className="space-y-2 max-h-48 overflow-y-auto pr-1">
                {pullRequests.map((pr) => {
                  const isSelected = selectedPRNumber === pr.number;
                  return (
                    <div
                      key={pr.number}
                      onClick={() => setSelectedPRNumber(pr.number)}
                      className={`p-3 rounded-xl border text-xs cursor-pointer transition-all ${
                        isSelected
                          ? 'bg-forge-600/20 border-forge-500/40 text-white'
                          : 'bg-surface-900/60 border-white/5 text-surface-300 hover:border-white/15 hover:bg-surface-800'
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-white">#{pr.number}: {pr.title}</span>
                        <span className="text-[10px] font-mono text-surface-500">by {pr.author}</span>
                      </div>
                      <div className="text-[11px] text-surface-400 font-mono mt-1">
                        {pr.source_branch} → {pr.target_branch}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {error && (
          <p className="text-xs text-red-300 bg-red-500/10 border border-red-500/20 px-3 py-2 rounded-xl">{error}</p>
        )}

        <div className="flex gap-3 pt-2">
          <Button variant="secondary" onClick={onClose} className="flex-1">
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={handleStartReview}
            disabled={!selectedRepoId || !selectedPRNumber || submitting}
            isLoading={submitting}
            className="flex-1"
          >
            Start Code Review
          </Button>
        </div>
      </div>
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export function CodeReviewsPage() {
  const { orgId: orgIdStr } = useParams<{ orgId: string }>();
  const navigate = useNavigate();
  const orgId = Number(orgIdStr);

  const [reviews, setReviews]           = useState<CodeReviewSummary[]>([]);
  const [repos, setRepos]               = useState<Repository[]>([]);
  const [loading, setLoading]           = useState(true);
  const [showStartModal, setShowStartModal] = useState(false);
  const [repoFilter, setRepoFilter]     = useState<number | undefined>(undefined);

  const loadData = useCallback(async () => {
    try {
      const [reviewRes, repoRes] = await Promise.all([
        reviewsApi.listReviews(orgId, { repository_id: repoFilter }),
        repositoryApi.listRepos(orgId),
      ]);
      setReviews(reviewRes.data.reviews || []);
      setRepos(repoRes.data.repositories || []);
    } catch (err) {
      console.error('Failed to load code reviews', err);
    } finally {
      setLoading(false);
    }
  }, [orgId, repoFilter]);

  useEffect(() => {
    loadData();
    // Poll reviews if any are queued or running
    const hasRunning = reviews.some(r => ['QUEUED', 'RUNNING'].includes(r.status));
    if (hasRunning) {
      const timer = setInterval(loadData, 3000);
      return () => clearInterval(timer);
    }
  }, [loadData, reviews]);

  const getRepoName = (repoId: number) => {
    return repos.find(r => r.id === repoId)?.full_name ?? `Repo #${repoId}`;
  };

  return (
    <PageLayout>
      <PageHeader
        title="AI Code Reviews"
        subtitle="Automated analysis of pull requests for security flaws, bugs, architecture issues, and missing tests."
        action={
          <Button
            variant="primary"
            size="md"
            onClick={() => setShowStartModal(true)}
            leftIcon={
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
            }
          >
            Review Pull Request
          </Button>
        }
      />

      {/* Filter Row */}
      {repos.length > 1 && (
        <div className="flex items-center gap-3 mb-6">
          <label className="text-xs text-surface-400 font-medium">Filter by repository:</label>
          <select
            value={repoFilter ?? ''}
            onChange={(e) => setRepoFilter(Number(e.target.value) || undefined)}
            className="bg-surface-850 border border-white/10 rounded-xl px-3 py-1.5 text-xs text-white focus:outline-none"
          >
            <option value="">All Repositories</option>
            {repos.map(r => (
              <option key={r.id} value={r.id}>
                {r.full_name}
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Reviews List */}
      {loading ? (
        <div className="flex justify-center py-20"><Spinner size="lg" /></div>
      ) : reviews.length === 0 ? (
        <Card>
          <div className="flex flex-col items-center justify-center py-16 text-center max-w-md mx-auto space-y-4">
            <div className="w-16 h-16 rounded-2xl bg-surface-800 border border-white/10 flex items-center justify-center text-purple-400">
              <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
                  d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
            </div>
            <h3 className="text-base font-bold text-white">No code reviews yet</h3>
            <p className="text-xs text-surface-400">
              Trigger an AI review on any pull request in your connected repositories to receive automated findings and severity scoring.
            </p>
            <Button variant="primary" onClick={() => setShowStartModal(true)}>
              Review a Pull Request
            </Button>
          </div>
        </Card>
      ) : (
        <div className="space-y-4">
          {reviews.map((rev) => {
            const isProcessing = ['QUEUED', 'RUNNING'].includes(rev.status);

            return (
              <div
                key={rev.id}
                onClick={() => navigate(`/organizations/${orgId}/reviews/${rev.id}`)}
                className="glass-card p-5 border border-white/10 hover:border-forge-500/40 transition-all cursor-pointer group space-y-3"
              >
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2.5 flex-wrap">
                      <span className="font-bold text-white text-sm group-hover:text-forge-300 transition-colors">
                        PR #{rev.pull_number}: {rev.pull_title}
                      </span>
                      <span className={`text-[10px] font-mono uppercase px-2 py-0.5 rounded-full border ${
                        rev.status === 'COMPLETED'
                          ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
                          : rev.status === 'FAILED'
                          ? 'bg-red-500/15 text-red-300 border-red-500/30'
                          : 'bg-amber-500/15 text-amber-300 border-amber-500/30 animate-pulse'
                      }`}>
                        {rev.status}
                      </span>
                      {rev.assessment && (
                        <span className="text-[10px] font-semibold text-purple-300 bg-purple-500/15 border border-purple-500/30 px-2 py-0.5 rounded-full">
                          {rev.assessment}
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-surface-400 font-mono">
                      {getRepoName(rev.repository_id)} · Created {new Date(rev.created_at).toLocaleString()}
                    </p>
                  </div>

                  {rev.overall_score !== null && (
                    <div className="flex items-center gap-2 bg-surface-900 border border-white/10 px-3.5 py-2 rounded-xl flex-shrink-0">
                      <span className="text-xs text-surface-400">Score</span>
                      <span className="text-sm font-extrabold text-white font-mono">
                        {rev.overall_score.toFixed(1)} / 10
                      </span>
                    </div>
                  )}
                </div>

                {/* Severity Breakdown */}
                {rev.status === 'COMPLETED' && rev.severity_counts && (
                  <div className="flex items-center gap-3 pt-2 border-t border-white/5 flex-wrap text-xs">
                    <span className="text-[11px] text-surface-500">Findings:</span>
                    {rev.severity_counts.critical > 0 && (
                      <span className="flex items-center gap-1 text-red-400 font-mono text-[11px]">
                        <SeverityBadge severity="CRITICAL" /> {rev.severity_counts.critical}
                      </span>
                    )}
                    {rev.severity_counts.high > 0 && (
                      <span className="flex items-center gap-1 text-orange-400 font-mono text-[11px]">
                        <SeverityBadge severity="HIGH" /> {rev.severity_counts.high}
                      </span>
                    )}
                    {rev.severity_counts.medium > 0 && (
                      <span className="flex items-center gap-1 text-amber-400 font-mono text-[11px]">
                        <SeverityBadge severity="MEDIUM" /> {rev.severity_counts.medium}
                      </span>
                    )}
                    {rev.severity_counts.low > 0 && (
                      <span className="flex items-center gap-1 text-blue-400 font-mono text-[11px]">
                        <SeverityBadge severity="LOW" /> {rev.severity_counts.low}
                      </span>
                    )}
                    <span className="text-surface-500 text-[11px] font-mono ml-auto">
                      Files reviewed: {rev.files_reviewed}
                    </span>
                  </div>
                )}

                {isProcessing && (
                  <div className="flex items-center gap-2 text-xs text-amber-400 pt-2 border-t border-white/5">
                    <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
                    <span>AI review agents analyzing diff and repository context…</span>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {showStartModal && (
        <StartReviewModal
          repos={repos}
          orgId={orgId}
          onClose={() => setShowStartModal(false)}
          onStarted={(newRev) => setReviews(prev => [newRev, ...prev])}
        />
      )}
    </PageLayout>
  );
}
