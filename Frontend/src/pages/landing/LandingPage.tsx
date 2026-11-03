import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';

export function LandingPage() {
  const { isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<'chat' | 'review' | 'tests' | 'planner'>('chat');

  return (
    <div className="min-h-screen bg-surface-950 text-surface-100 selection:bg-forge-600 selection:text-white flex flex-col">
      {/* ── Navigation ──────────────────────────────────────────────────────── */}
      <header className="border-b border-white/8 backdrop-blur-xl bg-surface-950/70 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-forge-500 to-forge-700 flex items-center justify-center shadow-lg shadow-forge-900/50 border border-white/10">
              <svg className="w-4 h-4 text-white" viewBox="0 0 24 24" fill="currentColor">
                <path d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
            </div>
            <span className="font-bold text-white text-base tracking-wide">
              Forge<span className="text-forge-400">AI</span>
            </span>
          </div>

          <nav className="hidden md:flex items-center gap-8 text-sm text-surface-400">
            <a href="#features" className="hover:text-white transition-colors">Features</a>
            <a href="#how-it-works" className="hover:text-white transition-colors">How It Works</a>
            <a href="#architecture" className="hover:text-white transition-colors">Architecture</a>
          </nav>

          <div className="flex items-center gap-3">
            {isAuthenticated ? (
              <button
                onClick={() => navigate('/dashboard')}
                className="px-4 py-2 rounded-xl bg-gradient-to-r from-forge-600 to-forge-700 hover:from-forge-500 hover:to-forge-600 text-white text-xs font-semibold shadow-md transition-all"
              >
                Go to Workspace →
              </button>
            ) : (
              <>
                <Link
                  to="/login"
                  className="px-4 py-2 rounded-xl text-surface-300 hover:text-white text-xs font-medium transition-colors"
                >
                  Sign In
                </Link>
                <Link
                  to="/register"
                  className="px-4 py-2 rounded-xl bg-gradient-to-r from-forge-600 to-forge-700 hover:from-forge-500 hover:to-forge-600 text-white text-xs font-semibold shadow-md shadow-forge-900/50 hover:shadow-forge-600/30 transition-all"
                >
                  Get Started Free
                </Link>
              </>
            )}
          </div>
        </div>
      </header>

      {/* ── Hero Section ────────────────────────────────────────────────────── */}
      <section className="relative overflow-hidden pt-20 pb-24 md:pt-28 md:pb-32 auth-bg border-b border-white/8">
        <div className="absolute inset-0 bg-grid-pattern opacity-25 pointer-events-none" />
        <div className="max-w-5xl mx-auto px-6 text-center relative z-10">
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-forge-600/10 border border-forge-500/30 text-forge-300 text-xs font-medium mb-8">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            AI Software Engineering Platform for Fast-Moving Teams
          </div>

          <h1 className="text-4xl md:text-6xl font-extrabold text-white tracking-tight leading-[1.15] mb-6">
            The AI engineering partner that{' '}
            <span className="text-gradient">understands your software</span>
          </h1>

          <p className="text-base md:text-lg text-surface-400 max-w-2xl mx-auto leading-relaxed mb-10">
            Stop searching blindly across repositories, pull requests, and legacy docs.
            ForgeAI connects to your GitHub repositories, indexes your code semantics,
            and assists your engineering team at every step of development.
          </p>

          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <Link
              to="/register"
              className="w-full sm:w-auto px-8 py-3.5 rounded-xl bg-gradient-to-r from-forge-600 to-forge-700 hover:from-forge-500 hover:to-forge-600 text-white font-semibold text-sm shadow-xl shadow-forge-900/60 hover:shadow-forge-600/40 transition-all flex items-center justify-center gap-2"
            >
              <span>Connect Your First Repository</span>
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
              </svg>
            </Link>
            <Link
              to="/login"
              className="w-full sm:w-auto px-6 py-3.5 rounded-xl bg-surface-900/80 hover:bg-surface-800 text-surface-200 border border-white/10 text-sm font-medium transition-all"
            >
              Sign In to Workspace
            </Link>
          </div>
        </div>

        {/* ── Interactive Platform Preview ───────────────────────────────────── */}
        <div className="max-w-5xl mx-auto px-6 mt-16 relative z-10">
          <div className="glass-card border border-white/10 rounded-2xl overflow-hidden shadow-2xl shadow-black/80">
            {/* Header / Tabs */}
            <div className="flex items-center justify-between px-6 py-3 bg-surface-900/90 border-b border-white/8 flex-wrap gap-2">
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full bg-red-500/80" />
                <div className="w-3 h-3 rounded-full bg-amber-500/80" />
                <div className="w-3 h-3 rounded-full bg-emerald-500/80" />
                <span className="text-xs text-surface-500 ml-2 font-mono">repo: acme/payment-service</span>
              </div>

              <div className="flex gap-1 bg-surface-950 p-1 rounded-xl border border-white/5">
                {[
                  { key: 'chat', label: 'AI Workspace' },
                  { key: 'review', label: 'PR Review' },
                  { key: 'tests', label: 'Test Assistant' },
                  { key: 'planner', label: 'Feature Plan' },
                ].map((tab) => (
                  <button
                    key={tab.key}
                    onClick={() => setActiveTab(tab.key as any)}
                    className={`px-3 py-1 rounded-lg text-xs font-medium transition-all ${
                      activeTab === tab.key
                        ? 'bg-forge-600 text-white shadow'
                        : 'text-surface-400 hover:text-white'
                    }`}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Tab Body */}
            <div className="p-6 md:p-8 bg-surface-900/60 min-h-[340px] text-left">
              {activeTab === 'chat' && (
                <div className="space-y-4">
                  <div className="flex gap-3">
                    <div className="w-7 h-7 rounded-full bg-forge-600 flex items-center justify-center text-xs font-bold text-white flex-shrink-0">
                      U
                    </div>
                    <div className="bg-forge-600/20 border border-forge-500/30 rounded-2xl px-4 py-2.5 text-xs text-white max-w-xl">
                      Where is stripe webhook signature verification implemented, and what happens when verification fails?
                    </div>
                  </div>

                  <div className="flex gap-3">
                    <div className="w-7 h-7 rounded-full bg-emerald-500 flex items-center justify-center text-xs font-bold text-white flex-shrink-0">
                      AI
                    </div>
                    <div className="bg-surface-800/80 border border-white/10 rounded-2xl p-4 text-xs text-surface-200 max-w-2xl space-y-3">
                      <p>
                        Stripe webhook signature verification is implemented in <code className="bg-surface-950 px-1.5 py-0.5 rounded text-forge-300">src/services/webhook_verifier.py</code>.
                      </p>
                      <div className="bg-surface-950 p-3 rounded-lg border border-white/8 font-mono text-[11px] text-purple-300">
                        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
                      </div>
                      <p className="text-surface-300">
                        When verification fails, it raises <code className="text-red-400">SignatureVerificationError</code> and returns HTTP 400 with a logged audit entry to prevent replay attacks.
                      </p>
                      <div className="pt-2 border-t border-white/5 flex items-center gap-2 text-[10px] text-surface-500 font-mono">
                        <span>Retrieved: src/services/webhook_verifier.py (lines 42–89)</span>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {activeTab === 'review' && (
                <div className="space-y-4">
                  <div className="flex items-center justify-between pb-3 border-b border-white/8">
                    <div>
                      <h4 className="text-sm font-semibold text-white">Pull Request #42: Add idempotency to refund endpoint</h4>
                      <p className="text-xs text-surface-400">Status: Completed · Assessment: Needs Attention</p>
                    </div>
                    <div className="px-3 py-1 bg-amber-500/20 text-amber-300 border border-amber-500/40 rounded-full text-xs font-bold">
                      Score: 7.8 / 10
                    </div>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <div className="bg-surface-800/60 border border-red-500/30 rounded-xl p-3.5 space-y-1.5">
                      <div className="flex items-center justify-between">
                        <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded bg-red-500/20 text-red-300 border border-red-500/40">
                          Critical · Bug
                        </span>
                        <span className="text-[11px] text-surface-500 font-mono">src/refund.py:84</span>
                      </div>
                      <p className="text-xs font-semibold text-white">Missing transaction rollback on gateway failure</p>
                      <p className="text-[11px] text-surface-400">If the payment gateway throws a socket timeout, the refund state is marked as processed without refunding Stripe.</p>
                    </div>

                    <div className="bg-surface-800/60 border border-cyan-500/30 rounded-xl p-3.5 space-y-1.5">
                      <div className="flex items-center justify-between">
                        <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded bg-cyan-500/20 text-cyan-300 border border-cyan-500/40">
                          Testing Gap
                        </span>
                        <span className="text-[11px] text-surface-500 font-mono">tests/test_refund.py</span>
                      </div>
                      <p className="text-xs font-semibold text-white">Missing test for duplicate idempotency key</p>
                      <p className="text-[11px] text-surface-400">Recommend adding a unit test verifying duplicate request returns the original cached response with 200 OK.</p>
                    </div>
                  </div>
                </div>
              )}

              {activeTab === 'tests' && (
                <div className="space-y-3 font-mono text-xs">
                  <div className="text-surface-400">
                    Generated pytest suite for <span className="text-forge-300">services/auth.py</span>:
                  </div>
                  <pre className="bg-surface-950 p-4 rounded-xl border border-white/10 text-emerald-300 text-[11px] overflow-x-auto leading-relaxed">
{`@pytest.mark.asyncio
async def test_verify_token_expired(auth_service):
    expired_jwt = create_mock_jwt(exp=time.time() - 3600)
    with pytest.raises(TokenExpiredException):
        await auth_service.verify_session(expired_jwt)

@pytest.mark.asyncio
async def test_org_tenant_isolation(auth_service, mock_db):
    user_a = create_user(org_id=1)
    res = await auth_service.check_access(user_a, target_org_id=2)
    assert res.allowed is False
    assert res.status_code == 403`}
                  </pre>
                </div>
              )}

              {activeTab === 'planner' && (
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-white">Plan: Multi-tenant Webhook Subscriptions (v1)</span>
                    <span className="px-2.5 py-0.5 rounded-full text-[10px] bg-amber-500/20 text-amber-300 border border-amber-500/40 font-mono">
                      Awaiting Approval
                    </span>
                  </div>
                  <div className="space-y-2">
                    {[
                      { step: '1', title: 'Create WebhookSubscription SQL Model', file: 'models/webhook.py', complexity: 'Low' },
                      { step: '2', title: 'Add dispatch retry worker with exponential backoff', file: 'workers/dispatch.py', complexity: 'Medium' },
                      { step: '3', title: 'Add API endpoints for subscription CRUD', file: 'api/routes/webhooks.py', complexity: 'Low' },
                    ].map((t) => (
                      <div key={t.step} className="bg-surface-800/80 border border-white/8 rounded-xl px-4 py-2.5 flex items-center justify-between text-xs">
                        <div className="flex items-center gap-3">
                          <span className="w-5 h-5 rounded-full bg-forge-600/30 text-forge-300 flex items-center justify-center font-mono text-[10px] font-bold">
                            {t.step}
                          </span>
                          <span className="text-white font-medium">{t.title}</span>
                          <span className="text-surface-500 font-mono text-[11px]">({t.file})</span>
                        </div>
                        <span className="text-surface-400 text-[10px] font-mono">{t.complexity}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </section>

      {/* ── Features Grid ───────────────────────────────────────────────────── */}
      <section id="features" className="py-24 max-w-7xl mx-auto px-6">
        <div className="text-center mb-16">
          <h2 className="text-xs font-mono uppercase tracking-widest text-forge-400 mb-2">Core Platform</h2>
          <p className="text-3xl font-bold text-white tracking-tight">Everything development teams need</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {[
            {
              icon: '🧠',
              title: 'Repository Intelligence',
              desc: 'Continuous ingestion via GitHub App. Token-aware chunking and vector indexing in Qdrant gives ForgeAI instant semantic recall across your entire codebase.',
            },
            {
              icon: '💬',
              title: 'Engineering AI Partner',
              desc: 'Ask questions about complex architectural patterns, discover where features are implemented, and understand service dependencies with exact file references.',
            },
            {
              icon: '🔍',
              title: 'Automated Code Review',
              desc: 'Deep AI inspection of pull requests for critical bugs, security vulnerabilities, architecture smells, and missing test coverage before merging.',
            },
            {
              icon: '🧪',
              title: 'Test Generation Assistant',
              desc: 'Pinpoint missing test cases in altered files or pull requests and generate production-grade unit and integration tests instantly.',
            },
            {
              icon: '🗺️',
              title: 'Feature Planner (LangGraph)',
              desc: 'Translate natural language product requirements into concrete engineering task graphs, affected file impact reports, and human-in-the-loop approvals.',
            },
            {
              icon: '🔒',
              title: 'Strict Multi-Tenant Isolation',
              desc: 'Organization-first security. Repositories and vector embeddings are strictly bounded to their organization tenant and never leaked across organizations.',
            },
          ].map((feature) => (
            <div key={feature.title} className="glass-card p-6 flex flex-col gap-3 group hover:border-forge-500/40 transition-all">
              <span className="text-3xl mb-1">{feature.icon}</span>
              <h3 className="text-base font-semibold text-white group-hover:text-forge-300 transition-colors">
                {feature.title}
              </h3>
              <p className="text-xs text-surface-400 leading-relaxed">
                {feature.desc}
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* ── Footer ──────────────────────────────────────────────────────────── */}
      <footer className="mt-auto border-t border-white/8 py-8 bg-surface-950">
        <div className="max-w-7xl mx-auto px-6 flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-surface-500">
          <div className="flex items-center gap-2">
            <span className="font-bold text-white">ForgeAI</span>
            <span>— AI Software Engineering Platform</span>
          </div>
          <div>
            <span>Built for modern engineering teams.</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
