import { useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Input, PasswordInput } from '@/components/ui/Input';
import { Button } from '@/components/ui/Button';
import { AxiosError } from 'axios';
import type { ApiError } from '@/types';

function StrengthBar({ password }: { password: string }) {
  const score = [/.{8,}/, /[A-Z]/, /[0-9]/, /[^A-Za-z0-9]/].filter((r) =>
    r.test(password),
  ).length;

  const labels = ['', 'Weak', 'Fair', 'Good', 'Strong'];
  const colors = ['', 'bg-red-500', 'bg-amber-500', 'bg-blue-500', 'bg-emerald-500'];

  if (!password) return null;

  return (
    <div className="flex flex-col gap-1.5 mt-1">
      <div className="flex gap-1">
        {[1, 2, 3, 4].map((i) => (
          <div
            key={i}
            className={`h-1 flex-1 rounded-full transition-all duration-300 ${
              i <= score ? colors[score] : 'bg-surface-700'
            }`}
          />
        ))}
      </div>
      {score > 0 && (
        <p className={`text-[11px] ${score < 2 ? 'text-red-400' : score < 3 ? 'text-amber-400' : score < 4 ? 'text-blue-400' : 'text-emerald-400'}`}>
          Password strength: {labels[score]}
        </p>
      )}
    </div>
  );
}

export function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();

  const [name, setName]         = useState('');
  const [email, setEmail]       = useState('');
  const [password, setPassword] = useState('');
  const [error, setError]       = useState('');
  const [loading, setLoading]   = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      await register({ name, email, password });
      navigate('/setup');  // redirect to org setup after registration
    } catch (err) {
      const axiosErr = err as AxiosError<ApiError>;
      const detail = axiosErr.response?.data?.detail;
      if (Array.isArray(detail)) {
        setError(detail.map((d) => d.msg).join('. '));
      } else {
        setError(typeof detail === 'string' ? detail : 'Registration failed. Please try again.');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex auth-bg">
      {/* ── Left panel ──────────────────────────────────────────── */}
      <div className="hidden lg:flex flex-col justify-between w-[50%] p-12 relative overflow-hidden bg-surface-900 border-r border-white/8">
        <div className="absolute inset-0 bg-grid-pattern opacity-25" />
        <div className="absolute top-1/3 left-1/3 w-80 h-80 bg-forge-600/15 rounded-full blur-3xl pointer-events-none" />

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

        {/* Steps preview */}
        <div className="relative space-y-6">
          <h2 className="text-3xl font-extrabold text-white leading-tight">
            Connect your software<br />
            <span className="text-gradient">in three easy steps.</span>
          </h2>

          <div className="flex flex-col gap-5 pt-2">
            {[
              { step: '01', title: 'Create Engineer Account', desc: 'Register with your developer work email.' },
              { step: '02', title: 'Set Up Organization Workspace', desc: 'Establish an isolated tenant workspace for your repositories.' },
              { step: '03', title: 'Authorize GitHub App & Sync', desc: 'Select repositories to index and interact with the AI Engineering Agent.' },
            ].map((s) => (
              <div key={s.step} className="flex items-start gap-4">
                <div className="w-9 h-9 rounded-xl bg-surface-800 border border-white/10 flex items-center justify-center text-forge-300 text-xs font-mono font-bold flex-shrink-0">
                  {s.step}
                </div>
                <div>
                  <p className="text-white font-semibold text-sm">{s.title}</p>
                  <p className="text-surface-400 text-xs mt-0.5">{s.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="relative text-surface-500 text-xs font-mono">
          ForgeAI Platform — Multi-Tenant Architecture & Granular Security
        </div>
      </div>

      {/* ── Right panel — register form ──────────────────────────── */}
      <div className="flex-1 flex items-center justify-center p-6 lg:p-12">
        <div className="w-full max-w-md animate-slide-up">
          <div className="mb-8">
            <h2 className="text-2xl font-bold text-white tracking-tight">Create your account</h2>
            <p className="text-surface-400 mt-1 text-sm">
              Get started with ForgeAI and empower your engineering team
            </p>
          </div>

          <form onSubmit={handleSubmit} className="flex flex-col gap-5">
            <Input
              label="Full name"
              id="register-name"
              type="text"
              placeholder="Alex Smith"
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoComplete="name"
              required
              leftIcon={
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                </svg>
              }
            />

            <Input
              label="Work email"
              id="register-email"
              type="email"
              placeholder="engineer@company.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
              required
              leftIcon={
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                </svg>
              }
            />

            <div className="flex flex-col gap-1.5">
              <PasswordInput
                label="Password"
                id="register-password"
                placeholder="At least 8 characters"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="new-password"
                required
                minLength={8}
              />
              <StrengthBar password={password} />
            </div>

            {error && (
              <div className="flex items-center gap-2 px-4 py-3 bg-red-500/10 border border-red-500/30 rounded-xl text-red-300 text-xs">
                <svg className="w-4 h-4 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                </svg>
                {error}
              </div>
            )}

            <Button type="submit" variant="primary" size="lg" isLoading={loading} className="mt-2">
              Create Developer Account
            </Button>
          </form>

          <p className="text-center text-xs text-surface-400 mt-6">
            Already have an account?{' '}
            <Link to="/login" className="text-forge-400 hover:text-forge-300 font-semibold transition-colors">
              Sign in
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
