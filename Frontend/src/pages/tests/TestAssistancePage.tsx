/**
 * TestAssistancePage — generate unit and integration tests for files and pull requests.
 */
import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { PageLayout, PageHeader } from '@/components/layout/PageLayout';
import { aiApi } from '@/api/ai';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { MarkdownRenderer } from '@/components/ui/MarkdownRenderer';
import { Spinner } from '@/components/ui/Spinner';
import type { Conversation } from '@/types';

export function TestAssistancePage() {
  const { orgId: orgIdStr } = useParams<{ orgId: string }>();
  const navigate = useNavigate();
  const orgId = Number(orgIdStr);

  const [conversations, setConversations]   = useState<Conversation[]>([]);
  const [selectedConvId, setSelectedConvId] = useState<string>('');
  const [targetMode, setTargetMode]         = useState<'file' | 'pr'>('file');
  const [filePath, setFilePath]             = useState('');
  const [pullNumber, setPullNumber]         = useState('');
  const [instructions, setInstructions]     = useState('');
  const [framework, setFramework]           = useState('pytest');
  const [loading, setLoading]               = useState(false);
  const [result, setResult]                 = useState<string | null>(null);
  const [error, setError]                   = useState('');

  useEffect(() => {
    if (!orgId) return;
    aiApi.listConversations(orgId)
      .then((convRes) => {
        const convList = convRes.data.conversations || [];
        setConversations(convList);
        if (convList.length > 0) {
          setSelectedConvId(convList[0].id);
        }
      })
      .catch(console.error);
  }, [orgId]);

  const handleGenerate = async () => {
    if (!selectedConvId) {
      setError('Please select an active conversation context.');
      return;
    }

    if (targetMode === 'file' && !filePath.trim()) {
      setError('Please provide a target file path in the repository.');
      return;
    }

    if (targetMode === 'pr' && !pullNumber.trim()) {
      setError('Please provide a pull request number.');
      return;
    }

    setLoading(true);
    setError('');
    setResult(null);

    const fullInstructions = [
      `Testing framework: ${framework}`,
      instructions.trim(),
    ].filter(Boolean).join('. ');

    try {
      const res = await aiApi.testAssistance(selectedConvId, {
        file_path: targetMode === 'file' ? filePath.trim() : undefined,
        pull_number: targetMode === 'pr' ? Number(pullNumber) : undefined,
        instructions: fullInstructions,
      });
      setResult(res.data.content);
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(typeof msg === 'string' ? msg : 'Test assistance request failed. Verify the file exists in the repository.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <PageLayout>
      <PageHeader
        title="Test Assistance"
        subtitle="Intelligent test synthesis: pinpoint missing test paths and generate complete test suites for files or pull requests."
        action={
          <Button
            variant="secondary"
            size="sm"
            onClick={() => navigate(`/organizations/${orgId}/ai`)}
          >
            ← Open AI Workspace
          </Button>
        }
      />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column: Form Settings */}
        <div className="lg:col-span-1 space-y-4">
          <Card>
            <h3 className="text-sm font-bold text-white mb-4 uppercase tracking-wider">Test Configuration</h3>

            <div className="space-y-4">
              {/* Conversation Selector */}
              <div>
                <label className="block text-xs font-medium text-surface-300 mb-1.5">
                  Conversation Context <span className="text-red-400">*</span>
                </label>
                {conversations.length === 0 ? (
                  <p className="text-xs text-amber-300 bg-amber-500/10 border border-amber-500/20 rounded-xl p-3">
                    No active conversations. Start one in AI Workspace first.
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

              {/* Target Type Toggle */}
              <div>
                <label className="block text-xs font-medium text-surface-300 mb-1.5">
                  Target Scope
                </label>
                <div className="grid grid-cols-2 gap-2 bg-surface-900 p-1 rounded-xl border border-white/5">
                  <button
                    type="button"
                    onClick={() => setTargetMode('file')}
                    className={`py-1.5 text-xs font-semibold rounded-lg transition-all ${
                      targetMode === 'file'
                        ? 'bg-forge-600 text-white shadow'
                        : 'text-surface-400 hover:text-white'
                    }`}
                  >
                    Specific File
                  </button>
                  <button
                    type="button"
                    onClick={() => setTargetMode('pr')}
                    className={`py-1.5 text-xs font-semibold rounded-lg transition-all ${
                      targetMode === 'pr'
                        ? 'bg-forge-600 text-white shadow'
                        : 'text-surface-400 hover:text-white'
                    }`}
                  >
                    Pull Request Diff
                  </button>
                </div>
              </div>

              {/* File Path or PR Number input */}
              {targetMode === 'file' ? (
                <div>
                  <label className="block text-xs font-medium text-surface-300 mb-1.5">
                    Target File Path <span className="text-red-400">*</span>
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. src/auth/jwt.py or app/services/order.ts"
                    value={filePath}
                    onChange={(e) => setFilePath(e.target.value)}
                    className="w-full bg-surface-900 border border-white/10 rounded-xl px-3 py-2 text-xs text-white placeholder-surface-500 focus:outline-none focus:ring-2 focus:ring-forge-500/40 font-mono"
                  />
                </div>
              ) : (
                <div>
                  <label className="block text-xs font-medium text-surface-300 mb-1.5">
                    Pull Request Number <span className="text-red-400">*</span>
                  </label>
                  <input
                    type="number"
                    placeholder="e.g. 42"
                    value={pullNumber}
                    onChange={(e) => setPullNumber(e.target.value)}
                    className="w-full bg-surface-900 border border-white/10 rounded-xl px-3 py-2 text-xs text-white placeholder-surface-500 focus:outline-none focus:ring-2 focus:ring-forge-500/40 font-mono"
                  />
                </div>
              )}

              {/* Framework selection */}
              <div>
                <label className="block text-xs font-medium text-surface-300 mb-1.5">
                  Testing Framework
                </label>
                <select
                  value={framework}
                  onChange={(e) => setFramework(e.target.value)}
                  className="w-full bg-surface-900 border border-white/10 rounded-xl px-3 py-2 text-xs text-white focus:outline-none"
                >
                  <option value="pytest">Python (pytest + pytest-asyncio)</option>
                  <option value="unittest">Python (unittest)</option>
                  <option value="jest">JavaScript/TypeScript (Jest)</option>
                  <option value="vitest">JavaScript/TypeScript (Vitest)</option>
                  <option value="go-test">Go (testing package)</option>
                </select>
              </div>

              {/* Custom Instructions */}
              <div>
                <label className="block text-xs font-medium text-surface-300 mb-1.5">
                  Custom Testing Instructions <span className="text-surface-500">(optional)</span>
                </label>
                <textarea
                  rows={3}
                  placeholder="e.g. Mock the database sessions, include edge cases for rate-limiting, test expired tokens"
                  value={instructions}
                  onChange={(e) => setInstructions(e.target.value)}
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
                onClick={handleGenerate}
                disabled={loading || conversations.length === 0}
                isLoading={loading}
              >
                Synthesize Tests
              </Button>
            </div>
          </Card>
        </div>

        {/* Right Column: Generated Test Suite */}
        <div className="lg:col-span-2">
          <Card className="min-h-[460px] flex flex-col">
            <div className="flex items-center justify-between pb-4 border-b border-white/8 mb-4">
              <h3 className="text-sm font-bold text-white uppercase tracking-wider">
                Generated Test Suite & Recommendations
              </h3>
              {result && (
                <span className="text-xs font-mono text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 rounded-full">
                  ● Generated by Testing Agent
                </span>
              )}
            </div>

            {loading ? (
              <div className="flex-1 flex flex-col items-center justify-center py-20 gap-3 text-center">
                <Spinner size="lg" />
                <p className="text-xs text-surface-400">
                  Inspecting file AST, dependencies, and generating test cases…
                </p>
              </div>
            ) : result ? (
              <div className="flex-1 overflow-y-auto pr-1">
                <MarkdownRenderer content={result} />
              </div>
            ) : (
              <div className="flex-1 flex flex-col items-center justify-center py-20 text-center max-w-sm mx-auto space-y-3">
                <div className="w-12 h-12 rounded-2xl bg-surface-800 border border-white/10 flex items-center justify-center text-cyan-400">
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
                      d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" />
                  </svg>
                </div>
                <h4 className="text-sm font-semibold text-white">No tests generated yet</h4>
                <p className="text-xs text-surface-400">
                  Select a target file or pull request on the left to synthesize edge-case unit and integration tests.
                </p>
              </div>
            )}
          </Card>
        </div>
      </div>
    </PageLayout>
  );
}
