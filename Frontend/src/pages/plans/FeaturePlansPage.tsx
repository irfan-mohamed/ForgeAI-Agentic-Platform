/**
 * FeaturePlansPage — LangGraph-driven autonomous Feature Planning with Human-in-the-loop gates.
 */
import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { PageLayout, PageHeader } from '@/components/layout/PageLayout';
import { plansApi } from '@/api/plans';
import { buildRunsApi } from '@/api/buildRuns';
import { aiApi } from '@/api/ai';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Spinner } from '@/components/ui/Spinner';
import type { Conversation, PlanData, PlanOut } from '@/types';

export function FeaturePlansPage() {
  const { orgId: orgIdStr } = useParams<{ orgId: string }>();
  const navigate = useNavigate();
  const orgId = Number(orgIdStr);

  const [conversations, setConversations]       = useState<Conversation[]>([]);
  const [selectedConvId, setSelectedConvId]     = useState<string>('');
  const [featureRequest, setFeatureRequest]     = useState('');
  const [generating, setGenerating]             = useState(false);
  const [currentPlan, setCurrentPlan]           = useState<PlanOut | null>(null);
  const [planData, setPlanData]                 = useState<PlanData | null>(null);
  const [error, setError]                       = useState('');
  const [feedback, setFeedback]                 = useState('');
  const [showFeedbackModal, setShowFeedbackModal] = useState(false);
  const [actionLoading, setActionLoading]       = useState(false);
  const [buildLoading, setBuildLoading]         = useState(false);

  useEffect(() => {
    if (!orgId) return;
    aiApi.listConversations(orgId)
      .then((res) => {
        const convList = res.data.conversations || [];
        setConversations(convList);
        if (convList.length > 0) setSelectedConvId(convList[0].id);
      })
      .catch(console.error);
  }, [orgId]);

  const handleGeneratePlan = async () => {
    if (!selectedConvId || !featureRequest.trim()) {
      setError('Please select a conversation and describe the feature.');
      return;
    }

    setGenerating(true);
    setError('');
    setCurrentPlan(null);
    setPlanData(null);

    try {
      const res = await plansApi.createPlan(selectedConvId, featureRequest.trim());
      if (res.data.status === 'failed') {
        setError(res.data.error_message || 'Planning failed. Please try again.');
      } else if (res.data.plan_id) {
        const fullPlan = await plansApi.getPlan(res.data.plan_id);
        setCurrentPlan(fullPlan.data);
        setPlanData(fullPlan.data.plan_data);
      }
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(typeof msg === 'string' ? msg : 'Failed to generate feature implementation plan.');
    } finally {
      setGenerating(false);
    }
  };

  const handleApprove = async () => {
    if (!currentPlan) return;
    setActionLoading(true);
    try {
      const updated = await plansApi.approvePlan(currentPlan.id);
      setCurrentPlan(updated.data);
    } catch (err: unknown) {
      alert('Failed to approve plan.');
    } finally {
      setActionLoading(false);
    }
  };

  const handleReject = async () => {
    if (!currentPlan || !confirm('Are you sure you want to reject this plan?')) return;
    setActionLoading(true);
    try {
      const updated = await plansApi.rejectPlan(currentPlan.id);
      setCurrentPlan(updated.data);
    } catch (err: unknown) {
      alert('Failed to reject plan.');
    } finally {
      setActionLoading(false);
    }
  };

  const handleRequestChanges = async () => {
    if (!currentPlan || !feedback.trim()) return;
    setActionLoading(true);
    try {
      const res = await plansApi.requestChanges(currentPlan.id, { feedback: feedback.trim() });
      if (res.data.plan_id) {
        const newPlan = await plansApi.getPlan(res.data.plan_id);
        setCurrentPlan(newPlan.data);
        setPlanData(newPlan.data.plan_data);
        setShowFeedbackModal(false);
        setFeedback('');
      }
    } catch (err: unknown) {
      alert('Failed to submit feedback.');
    } finally {
      setActionLoading(false);
    }
  };

  /** Trigger Phase 4 Build Execution and navigate to BuildRunPage. */
  const handleBuild = async () => {
    if (!currentPlan) return;
    setBuildLoading(true);
    try {
      const res = await buildRunsApi.triggerBuild(currentPlan.id);
      navigate(`/organizations/${orgId}/build-runs/${res.data.build_run_id}`);
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      alert(typeof msg === 'string' ? msg : 'Failed to trigger build run.');
    } finally {
      setBuildLoading(false);
    }
  };

  return (
    <PageLayout>
      <PageHeader
        title="Autonomous Feature Planner"
        subtitle="LangGraph-powered architectural investigation, affected file discovery, task breakdown, and Human-in-the-Loop review."
        action={
          <Button
            variant="secondary"
            size="sm"
            onClick={() => navigate(`/organizations/${orgId}/ai`)}
          >
            ← AI Workspace
          </Button>
        }
      />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column: Create Plan Request */}
        <div className="lg:col-span-1 space-y-4">
          <Card>
            <h3 className="text-sm font-bold text-white mb-4 uppercase tracking-wider">
              Feature Specification
            </h3>

            <div className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-surface-300 mb-1.5">
                  Conversation Context <span className="text-red-400">*</span>
                </label>
                {conversations.length === 0 ? (
                  <p className="text-xs text-amber-300 bg-amber-500/10 border border-amber-500/20 rounded-xl p-3">
                    No active conversations. Connect a repo and start an investigation first.
                  </p>
                ) : (
                  <select
                    value={selectedConvId}
                    onChange={(e) => setSelectedConvId(e.target.value)}
                    className="w-full bg-surface-900 border border-white/10 rounded-xl px-3 py-2 text-xs text-white focus:outline-none focus:ring-2 focus:ring-forge-500/40"
                  >
                    {conversations.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.title}
                      </option>
                    ))}
                  </select>
                )}
              </div>

              <div>
                <label className="block text-xs font-medium text-surface-300 mb-1.5">
                  Natural Language Feature Request <span className="text-red-400">*</span>
                </label>
                <textarea
                  rows={4}
                  placeholder="e.g. Implement multi-tenant webhook subscriptions with HMAC signature verification and exponential backoff retry worker."
                  value={featureRequest}
                  onChange={(e) => setFeatureRequest(e.target.value)}
                  className="input-base text-xs resize-none"
                />
              </div>

              {error && (
                <p className="text-xs text-red-300 bg-red-500/10 border border-red-500/20 p-3 rounded-xl">
                  {error}
                </p>
              )}

              <Button
                variant="primary"
                onClick={handleGeneratePlan}
                disabled={generating || !featureRequest.trim() || !selectedConvId}
                isLoading={generating}
              >
                Generate Implementation Plan
              </Button>
            </div>
          </Card>
        </div>

        {/* Right Column: Interactive Plan Review & Gate */}
        <div className="lg:col-span-2">
          <Card className="min-h-[500px] flex flex-col">
            <div className="flex items-center justify-between pb-4 border-b border-white/8 mb-5">
              <div>
                <h3 className="text-sm font-bold text-white uppercase tracking-wider">
                  Implementation Plan Review
                </h3>
                {currentPlan && (
                  <p className="text-xs text-surface-400 font-mono mt-0.5">
                    Plan ID: {currentPlan.id.slice(0, 8)} · Version {currentPlan.version}
                  </p>
                )}
              </div>

              {currentPlan && (
                <span className={`badge font-mono text-[10px] uppercase ${
                  currentPlan.status === 'approved'
                    ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                    : currentPlan.status === 'rejected'
                    ? 'bg-red-500/20 text-red-300 border border-red-500/40'
                    : currentPlan.status === 'changes_requested'
                    ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                    : 'bg-purple-500/20 text-purple-300 border border-purple-500/40 animate-pulse'
                }`}>
                  {currentPlan.status.replace('_', ' ')}
                </span>
              )}
            </div>

            {generating ? (
              <div className="flex-1 flex flex-col items-center justify-center py-20 gap-3 text-center">
                <Spinner size="lg" />
                <p className="text-xs text-surface-300 font-medium">
                  LangGraph agent executing repository inspection tools…
                </p>
                <p className="text-[11px] text-surface-500 max-w-sm">
                  Analyzing dependency trees, affected files, and sequencing discrete engineering tasks.
                </p>
              </div>
            ) : currentPlan && planData ? (
              <div className="flex-1 overflow-y-auto space-y-6 pr-1">
                {/* Overview */}
                {planData.overview && (
                  <div className="bg-surface-900/60 p-4 rounded-xl border border-white/5 space-y-1">
                    <h4 className="text-xs font-bold text-white uppercase tracking-wider">Overview</h4>
                    <p className="text-xs text-surface-300 leading-relaxed">{planData.overview}</p>
                  </div>
                )}

                {/* Affected Files */}
                {planData.affected_files && planData.affected_files.length > 0 && (
                  <div className="space-y-2">
                    <h4 className="text-xs font-bold text-white uppercase tracking-wider">
                      Affected Files ({planData.affected_files.length})
                    </h4>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                      {planData.affected_files.map((file, i) => (
                        <div key={i} className="p-3 bg-surface-900 rounded-xl border border-white/5 text-xs">
                          <div className="flex items-center justify-between mb-1">
                            <span className="font-mono text-forge-300 truncate font-semibold">{file.file_path}</span>
                            <span className="text-[10px] font-mono uppercase text-surface-500">{file.change_type}</span>
                          </div>
                          <p className="text-[11px] text-surface-400 line-clamp-2">{file.reason}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Sequenced Task Breakdown */}
                {planData.tasks && planData.tasks.length > 0 && (
                  <div className="space-y-2.5">
                    <h4 className="text-xs font-bold text-white uppercase tracking-wider">
                      Sequenced Implementation Tasks ({planData.tasks.length})
                    </h4>
                    <div className="space-y-2">
                      {planData.tasks.map((task, idx) => (
                        <div key={task.id || idx} className="p-3.5 bg-surface-900 rounded-xl border border-white/5 space-y-1.5">
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2">
                              <span className="w-5 h-5 rounded-full bg-forge-600/30 text-forge-300 flex items-center justify-center font-mono text-[10px] font-bold">
                                {idx + 1}
                              </span>
                              <span className="font-semibold text-xs text-white">{task.title}</span>
                            </div>
                            <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded bg-surface-800 text-surface-400 border border-white/5">
                              {task.estimated_complexity} complexity
                            </span>
                          </div>
                          <p className="text-xs text-surface-400 pl-7">{task.description}</p>
                          <p className="text-[11px] font-mono text-surface-500 pl-7">
                            Target: <span className="text-forge-400">{task.file_path}</span>
                          </p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Human-in-the-Loop Gate Actions */}
                {currentPlan.status === 'awaiting_approval' && (
                  <div className="p-4 bg-surface-900 border border-forge-500/30 rounded-2xl flex flex-col sm:flex-row items-center justify-between gap-3 mt-6">
                    <div>
                      <h4 className="text-xs font-bold text-white">Human Approval Gate</h4>
                      <p className="text-[11px] text-surface-400">Review the tasks before marking the plan as approved.</p>
                    </div>

                    <div className="flex items-center gap-2 w-full sm:w-auto">
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => setShowFeedbackModal(true)}
                        disabled={actionLoading}
                      >
                        Request Changes
                      </Button>
                      <Button
                        variant="danger"
                        size="sm"
                        onClick={handleReject}
                        disabled={actionLoading}
                      >
                        Reject
                      </Button>
                      <Button
                        variant="primary"
                        size="sm"
                        onClick={handleApprove}
                        isLoading={actionLoading}
                      >
                        Approve Plan ✓
                      </Button>
                    </div>
                  </div>
                )}

                {/* Phase 4: Build, Test & PR */}
                {currentPlan?.status === 'approved' && (
                  <div className="pt-4 border-t border-white/8">
                    <div className="flex items-start gap-3 p-3 rounded-xl bg-emerald-500/8 border border-emerald-500/20 mb-3">
                      <span className="text-emerald-400 mt-0.5">&#10003;</span>
                      <div>
                        <p className="text-xs font-semibold text-emerald-300">Plan Approved</p>
                        <p className="text-[11px] text-surface-400 mt-0.5">
                          Ready to build, run integration tests, and auto-open a Pull Request.
                        </p>
                      </div>
                    </div>
                    <Button
                      variant="primary"
                      size="sm"
                      onClick={handleBuild}
                      isLoading={buildLoading}
                      className="w-full"
                    >
                      Build, Test &amp; Open PR
                    </Button>
                  </div>
                )}
              </div>
            ) : (
              <div className="flex-1 flex flex-col items-center justify-center py-20 text-center max-w-sm mx-auto space-y-3">
                <div className="w-12 h-12 rounded-2xl bg-surface-800 border border-white/10 flex items-center justify-center text-purple-400">
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
                      d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7" />
                  </svg>
                </div>
                <h4 className="text-sm font-semibold text-white">No feature plan active</h4>
                <p className="text-xs text-surface-400">
                  Enter a feature requirement on the left to autonomously map dependencies, affected files, and generate an actionable plan.
                </p>
              </div>
            )}
          </Card>
        </div>
      </div>

      {/* Request Changes Modal */}
      {showFeedbackModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-md glass-card p-6 border border-white/10 shadow-2xl animate-slide-up space-y-4">
            <h3 className="text-sm font-bold text-white">Request Plan Changes</h3>
            <p className="text-xs text-surface-400">
              Provide feedback on what needs revision. The planner agent will incorporate your feedback into a revised plan version.
            </p>
            <textarea
              rows={4}
              placeholder="e.g. Also include database migration steps and rate-limiting middleware in the task breakdown."
              value={feedback}
              onChange={(e) => setFeedback(e.target.value)}
              className="input-base text-xs resize-none"
            />
            <div className="flex gap-2 justify-end">
              <Button variant="secondary" size="sm" onClick={() => setShowFeedbackModal(false)}>
                Cancel
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={handleRequestChanges}
                disabled={!feedback.trim() || actionLoading}
                isLoading={actionLoading}
              >
                Submit Feedback & Revise
              </Button>
            </div>
          </div>
        </div>
      )}
    </PageLayout>
  );
}
