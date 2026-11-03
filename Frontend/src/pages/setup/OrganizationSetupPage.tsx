import { useState } from 'react';
import type { FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { organizationsApi } from '@/api/organizations';
import { Input } from '@/components/ui/Input';
import { Button } from '@/components/ui/Button';
import { AxiosError } from 'axios';
import type { ApiError } from '@/types';

// Auto-generate a slug from the org name
function toSlug(name: string): string {
  return name
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9\s-]/g, '')
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-')
    .slice(0, 50);
}

export function OrganizationSetupPage() {
  const navigate = useNavigate();

  const [name, setName]               = useState('');
  const [slug, setSlug]               = useState('');
  const [description, setDescription] = useState('');
  const [slugEdited, setSlugEdited]   = useState(false);
  const [error, setError]             = useState('');
  const [loading, setLoading]         = useState(false);

  const handleNameChange = (value: string) => {
    setName(value);
    if (!slugEdited) {
      setSlug(toSlug(value));
    }
  };

  const handleSlugChange = (value: string) => {
    setSlugEdited(true);
    setSlug(value.toLowerCase().replace(/[^a-z0-9-]/g, ''));
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const res = await organizationsApi.create({ name, slug, description: description || undefined });
      // Redirect straight to repositories page to connect GitHub
      navigate(`/organizations/${res.data.id}/repositories`);
    } catch (err) {
      const axiosErr = err as AxiosError<ApiError>;
      const detail = axiosErr.response?.data?.detail;
      setError(
        Array.isArray(detail)
          ? detail.map((d) => d.msg).join('. ')
          : typeof detail === 'string'
          ? detail
          : 'Failed to create organization. Please try again.',
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center auth-bg p-6">
      <div className="w-full max-w-lg animate-slide-up">
        {/* Header */}
        <div className="text-center mb-8">
          <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-forge-500 to-forge-700 flex items-center justify-center mx-auto mb-4 shadow-xl shadow-forge-900/40 border border-white/10">
            <svg className="w-7 h-7 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
                d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
            </svg>
          </div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Create your engineering workspace</h1>
          <p className="text-surface-400 text-xs mt-2">
            Organizations provide strict tenant isolation for your repositories and AI knowledge.
          </p>
        </div>

        {/* Form Card */}
        <div className="glass-card p-8 border border-white/10">
          <form onSubmit={handleSubmit} className="flex flex-col gap-5">
            <Input
              label="Organization Name"
              id="org-name"
              type="text"
              placeholder="e.g. Acme Engineering"
              value={name}
              onChange={(e) => handleNameChange(e.target.value)}
              required
              hint="The name of your engineering department, startup, or team."
            />

            <div>
              <Input
                label="Workspace Slug"
                id="org-slug"
                type="text"
                placeholder="acme-engineering"
                value={slug}
                onChange={(e) => handleSlugChange(e.target.value)}
                required
                hint="Unique URL identifier. Lowercase letters, numbers, and hyphens."
                leftIcon={
                  <span className="text-surface-500 text-xs font-mono">forge/</span>
                }
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label htmlFor="org-description" className="text-xs font-medium text-surface-300">
                Description <span className="text-surface-500 font-normal">(optional)</span>
              </label>
              <textarea
                id="org-description"
                rows={3}
                placeholder="What software does this workspace build and maintain?"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                className="input-base resize-none"
              />
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
              Create Workspace & Continue
            </Button>
          </form>
        </div>

        <p className="text-center text-xs text-surface-500 mt-6">
          You will automatically become the initial workspace owner.
        </p>
      </div>
    </div>
  );
}
