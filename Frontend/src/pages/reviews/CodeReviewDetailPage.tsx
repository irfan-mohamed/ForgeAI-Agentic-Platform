/**
 * CodeReviewDetailPage — full AI findings, severity inspection, and recommendations.
 */
import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { PageLayout, PageHeader } from '@/components/layout/PageLayout';
import { reviewsApi } from '@/api/reviews';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { SeverityBadge, CategoryBadge } from '@/components/ui/Badge';
import { Spinner } from '@/components/ui/Spinner';
import { MarkdownRenderer } from '@/components/ui/MarkdownRenderer';
import type { CodeReviewDetail, ReviewFinding } from '@/types';

export function CodeReviewDetailPage() {
  const { orgId, reviewId } = useParams<{ orgId: string; reviewId: string }>();
  const navigate = useNavigate();

  const [review, setReview]               = useState<CodeReviewDetail | null>(null);
  const [loading, setLoading]             = useState(true);
  const [error, setError]                 = useState('');
  const [severityFilter, setSeverityFilter] = useState<string>('ALL');
  const [categoryFilter, setCategoryFilter] = useState<string>('ALL');

  useEffect(() => {
    if (!reviewId) return;
    setLoading(true);
    reviewsApi.getReview(reviewId)
      .then((res) => setReview(res.data))
      .catch(() => setError('Failed to load code review details.'))
      .finally(() => setLoading(false));
  }, [reviewId]);

  if (loading) {
    return (
      <PageLayout>
        <div className="flex items-center justify-center h-64">
          <Spinner size="lg" />
        </div>
      </PageLayout>
    );
  }

  if (error || !review) {
    return (
      <PageLayout>
        <Card>
          <div className="text-center py-12 space-y-4">
            <p className="text-red-400 text-sm">{error || 'Review not found.'}</p>
            <Button variant="secondary" onClick={() => navigate(`/organizations/${orgId}/reviews`)}>
              ← Back to Code Reviews
            </Button>
          </div>
        </Card>
      </PageLayout>
    );
  }

  const filteredFindings = review.findings?.filter((f: ReviewFinding) => {
    const matchesSev = severityFilter === 'ALL' || f.severity.toUpperCase() === severityFilter;
    const matchesCat = categoryFilter === 'ALL' || f.category.toUpperCase() === categoryFilter;
    return matchesSev && matchesCat;
  }) || [];

  return (
    <PageLayout>
      <PageHeader
        title={`Review: PR #${review.pull_number} — ${review.pull_title}`}
        subtitle={`Completed ${new Date(review.created_at).toLocaleString()} · Head SHA: ${review.head_sha?.slice(0, 7) || 'latest'}`}
        action={
          <div className="flex items-center gap-3">
            {review.pull_url && (
              <a
                href={review.pull_url}
                target="_blank"
                rel="noreferrer"
                className="px-3 py-2 rounded-xl bg-surface-800 hover:bg-surface-700 text-white text-xs border border-white/10 flex items-center gap-1.5 transition-colors"
              >
                <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M12 0C5.374 0 0 5.373 0 12c0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23A11.509 11.509 0 0112 5.803c1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576C20.566 21.797 24 17.3 24 12c0-6.627-5.373-12-12-12z"/>
                </svg>
                View on GitHub ↗
              </a>
            )}
            <Button
              variant="secondary"
              size="sm"
              onClick={() => navigate(`/organizations/${orgId}/reviews`)}
            >
              ← Back to Reviews
            </Button>
          </div>
        }
      />

      {/* Review Score & Overview Banner */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
        {/* Score Card */}
        <div className="glass-card p-6 border border-white/10 flex flex-col justify-center items-center text-center">
          <span className="text-xs font-semibold text-surface-400 uppercase tracking-wider mb-2">
            Overall Assessment Score
          </span>
          <div className="text-4xl font-extrabold text-white font-mono tracking-tight mb-2">
            {review.overall_score !== null ? `${review.overall_score.toFixed(1)} / 10` : '—'}
          </div>
          {review.assessment && (
            <span className="text-xs font-semibold px-3 py-1 rounded-full bg-purple-500/20 text-purple-300 border border-purple-500/30">
              {review.assessment}
            </span>
          )}
        </div>

        {/* Severity Metrics */}
        <div className="md:col-span-3 glass-card p-6 border border-white/10 flex flex-col justify-between">
          <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
            <span className="text-xs font-semibold text-surface-400 uppercase tracking-wider">
              Findings Severity Breakdown
            </span>
            <span className="text-xs font-mono text-surface-500">
              {review.files_reviewed} files analyzed ({review.files_omitted} omitted)
            </span>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="bg-surface-900 p-3 rounded-xl border border-red-500/30 text-center">
              <span className="text-red-400 text-xs font-mono font-bold block mb-1">CRITICAL</span>
              <span className="text-2xl font-black text-white">{review.severity_counts?.critical || 0}</span>
            </div>
            <div className="bg-surface-900 p-3 rounded-xl border border-orange-500/30 text-center">
              <span className="text-orange-400 text-xs font-mono font-bold block mb-1">HIGH</span>
              <span className="text-2xl font-black text-white">{review.severity_counts?.high || 0}</span>
            </div>
            <div className="bg-surface-900 p-3 rounded-xl border border-amber-500/30 text-center">
              <span className="text-amber-400 text-xs font-mono font-bold block mb-1">MEDIUM</span>
              <span className="text-2xl font-black text-white">{review.severity_counts?.medium || 0}</span>
            </div>
            <div className="bg-surface-900 p-3 rounded-xl border border-blue-500/30 text-center">
              <span className="text-blue-400 text-xs font-mono font-bold block mb-1">LOW / INFO</span>
              <span className="text-2xl font-black text-white">
                {(review.severity_counts?.low || 0) + (review.severity_counts?.info || 0)}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Summary Narrative */}
      {review.summary && (
        <Card className="mb-8">
          <h3 className="text-sm font-bold text-white mb-2 uppercase tracking-wider">AI Executive Summary</h3>
          <div className="text-xs leading-relaxed text-surface-300">
            <MarkdownRenderer content={review.summary} />
          </div>
        </Card>
      )}

      {/* Findings Section */}
      <div className="space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-2 border-b border-white/8">
          <div>
            <h3 className="text-base font-bold text-white">Detailed Findings ({filteredFindings.length})</h3>
            <p className="text-xs text-surface-400">Inspected code discrepancies, security patterns, and testing omissions</p>
          </div>

          {/* Filters */}
          <div className="flex items-center gap-3 flex-wrap">
            <div className="flex items-center gap-1.5 text-xs text-surface-400">
              <span>Severity:</span>
              <select
                value={severityFilter}
                onChange={(e) => setSeverityFilter(e.target.value)}
                className="bg-surface-850 border border-white/10 rounded-xl px-2.5 py-1 text-xs text-white focus:outline-none"
              >
                <option value="ALL">All Severities</option>
                <option value="CRITICAL">Critical</option>
                <option value="HIGH">High</option>
                <option value="MEDIUM">Medium</option>
                <option value="LOW">Low</option>
              </select>
            </div>

            <div className="flex items-center gap-1.5 text-xs text-surface-400">
              <span>Category:</span>
              <select
                value={categoryFilter}
                onChange={(e) => setCategoryFilter(e.target.value)}
                className="bg-surface-850 border border-white/10 rounded-xl px-2.5 py-1 text-xs text-white focus:outline-none"
              >
                <option value="ALL">All Categories</option>
                <option value="SECURITY">Security</option>
                <option value="BUG">Bug</option>
                <option value="TESTING">Testing</option>
                <option value="ARCHITECTURE">Architecture</option>
                <option value="MAINTAINABILITY">Maintainability</option>
              </select>
            </div>
          </div>
        </div>

        {filteredFindings.length === 0 ? (
          <div className="glass-card p-12 text-center text-xs text-surface-400 border border-white/10">
            No findings match the selected severity and category filters.
          </div>
        ) : (
          filteredFindings.map((finding, idx) => (
            <div
              key={finding.id || idx}
              className="glass-card p-5 border border-white/10 hover:border-forge-500/40 transition-all space-y-3"
            >
              <div className="flex items-start justify-between gap-3 flex-wrap">
                <div className="space-y-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <SeverityBadge severity={finding.severity} />
                    <CategoryBadge category={finding.category} />
                    <h4 className="text-sm font-bold text-white">{finding.title}</h4>
                  </div>
                  {finding.file_path && (
                    <p className="text-xs font-mono text-forge-300">
                      {finding.file_path}
                      {finding.line_start !== null && (
                        <span> (L{finding.line_start}{finding.line_end ? `–L${finding.line_end}` : ''})</span>
                      )}
                    </p>
                  )}
                </div>
              </div>

              {/* Description */}
              <p className="text-xs text-surface-300 leading-relaxed">
                {finding.description}
              </p>

              {/* Recommendation */}
              {finding.recommendation && (
                <div className="bg-surface-900/90 border border-white/8 rounded-xl p-3.5 space-y-1.5">
                  <span className="text-[11px] font-semibold text-emerald-400 uppercase tracking-wider block">
                    Actionable AI Recommendation:
                  </span>
                  <div className="text-xs text-surface-200">
                    <MarkdownRenderer content={finding.recommendation} />
                  </div>
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </PageLayout>
  );
}
