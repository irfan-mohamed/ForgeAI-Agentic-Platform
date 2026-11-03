import { useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Input, PasswordInput } from '@/components/ui/Input';
import { Button } from '@/components/ui/Button';
import { AxiosError } from 'axios';
import type { ApiError } from '@/types';

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();

  const [email, setEmail]       = useState('');
  const [password, setPassword] = useState('');
  const [error, setError]       = useState('');
  const [loading, setLoading]   = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      await login({ email, password });
      navigate('/dashboard');
    } catch (err) {
      const axiosErr = err as AxiosError<ApiError>;
      const detail = axiosErr.response?.data?.detail;
      setError(
        typeof detail === 'string'
          ? detail
          : 'Invalid email or password. Please try again.',
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex auth-bg">
      {/* ── Left panel — ForgeAI Developer Identity ──────────────── */}
      <div className="hidden lg:flex flex-col justify-between w-[50%] p-12 relative overflow-hidden bg-surface-900 border-r border-white/8">
        <div className="absolute inset-0 bg-grid-pattern opacity-25" />
        <div className="absolute top-1/4 left-1/4 w-72 h-72 bg-forge-600/15 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute bottom-1/4 right-1/4 w-60 h-60 bg-cyan-500/10 rounded-full blur-3xl pointer-events-none" />

        {/* Logo */}
        <div className="relative flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-forge-500 to-forge-700 flex items-center justify-center shadow-lg shadow-forge-900/50 border border-white/10">
            <svg className="w-5 h-5 text-white" viewBox="0 0 24 24" fill="currentColor">
              <path d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
          </div>
          <span className="font-bold text-white text-lg tracking-wide">
            Forge<span className="text-forge-400">AI</span>
          </span>
        </div>

        {/* Hero text */}
        <div className="relative space-y-6">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-forge-600/20 border border-forge-500/30 text-forge-300 text-xs font-mono">
            <span>●</span> AI Software Engineering Platform
          </div>

          <h1 className="text-4xl font-extrabold text-white leading-tight">
            Codebase intelligence<br />
            <span className="text-gradient">at engineering scale.</span>
          </h1>

          <p className="text-surface-400 text-sm leading-relaxed max-w-md">
            Connect your repositories, index code semantics with vector RAG, and accelerate code reviews, test writing, and architectural discovery.
          </p>

          {/* Highlights */}
          <div className="space-y-3 pt-2">
            {[
              { icon: '📦', text: 'GitHub App integration with granular repository access' },
              { icon: '⚡', text: 'Real-time semantic search & RAG over your source tree' },
              { icon: '🛡️', text: 'Automated PR code reviews with severity findings' },
              { icon: '🧪', text: 'Intelligent test generation for edge cases and gaps' },
            ].map((f) => (
              <div key={f.text} className="flex items-center gap-3 text-xs text-surface-300">
                <span className="text-base">{f.icon}</span>
                <span>{f.text}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Code Snippet Card */}
        <div className="relative glass-card p-4 max-w-md font-mono text-xs border border-white/10 text-surface-300">
          <div className="flex items-center justify-between text-surface-500 text-[11px] mb-2 border-b border-white/5 pb-1">
            <span>forgeai-agent v1.0</span>
            <span className="text-emerald-400">● 1,284 chunks indexed</span>
          </div>
          <p className="text-forge-300">"Auth token rotation is handled in <span className="text-white">services/auth/jwt.py:54</span> with automatic fallback to refreshed credentials."</p>
        </div>
      </div>

      {/* ── Right panel — Sign In Form ───────────────────────────── */}
      <div className="flex-1 flex items-center justify-center p-6 lg:p-12">
        <div className="w-full max-w-md animate-slide-up">
          <div className="mb-8">
            <h2 className="text-2xl font-bold text-white tracking-tight">Sign in to ForgeAI</h2>
            <p className="text-surface-400 mt-1 text-sm">
              Enter your credentials to access your engineering workspace
            </p>
          </div>

          <form onSubmit={handleSubmit} className="flex flex-col gap-5">
            <Input
              label="Work Email"
              id="login-email"
              type="email"
              placeholder="engineer@company.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
              required
              leftIcon={
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 12a4 4 0 10-8 0 4 4 0 008 0zm0 0v1.5a2.5 2.5 0 005 0V12a9 9 0 10-9 9m4.5-1.206a8.959 8.959 0 01-4.5 1.207" />
                </svg>
              }
            />

            <PasswordInput
              label="Password"
              id="login-password"
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
            />

            {error && (
              <div className="flex items-center gap-2 px-4 py-3 bg-red-500/10 border border-red-500/30 rounded-xl text-red-300 text-xs">
                <svg className="w-4 h-4 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                </svg>
                {error}
              </div>
            )}

            <Button type="submit" variant="primary" size="lg" isLoading={loading} className="mt-2">
              Sign In
            </Button>
          </form>

          <p className="text-center text-xs text-surface-400 mt-6">
            Don't have an account?{' '}
            <Link to="/register" className="text-forge-400 hover:text-forge-300 font-semibold transition-colors">
              Create an account
            </Link>
          </p>

          <p className="text-center text-xs text-surface-600 mt-4">
            <Link to="/" className="hover:text-surface-400 transition-colors">
              ← Back to homepage
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
