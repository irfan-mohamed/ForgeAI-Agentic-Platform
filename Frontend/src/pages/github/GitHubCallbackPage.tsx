/**
 * GitHubCallbackPage — handles the redirect from GitHub after App installation.
 *
 * GitHub redirects to: /github/callback?org_id=1&status=connected
 * (or ?status=error if something went wrong)
 *
 * This page reads the query params and redirects the user into the
 * repository connection flow.
 */
import { useEffect, useState } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { Spinner } from '@/components/ui/Spinner';

export function GitHubCallbackPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [message, setMessage] = useState('Connecting GitHub…');
  const [isError, setIsError] = useState(false);

  useEffect(() => {
    const status = params.get('status');
    const orgId  = params.get('org_id');

    if (status === 'connected' && orgId) {
      setMessage('GitHub connected! Redirecting…');
      setTimeout(() => {
        navigate(`/organizations/${orgId}/repositories`, { replace: true });
      }, 1200);
    } else {
      setIsError(true);
      setMessage(
        'GitHub connection failed. Please go back and try again.',
      );
    }
  }, [params, navigate]);

  return (
    <div className="min-h-screen flex flex-col items-center justify-center auth-bg gap-6">
      <div
        className={`w-16 h-16 rounded-2xl flex items-center justify-center ${
          isError
            ? 'bg-red-100 text-red-600'
            : 'bg-forge-100 text-forge-600'
        }`}
      >
        {isError ? (
          <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M6 18L18 6M6 6l12 12" />
          </svg>
        ) : (
          <svg className="w-8 h-8" fill="currentColor" viewBox="0 0 24 24">
            <path d="M12 0C5.374 0 0 5.373 0 12c0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23A11.509 11.509 0 0112 5.803c1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576C20.566 21.797 24 17.3 24 12c0-6.627-5.373-12-12-12z"/>
          </svg>
        )}
      </div>

      <div className="text-center">
        <p className="text-gray-700 font-medium">{message}</p>
        {!isError && <Spinner size="sm" className="mt-4 mx-auto" />}
      </div>

      {isError && (
        <button
          onClick={() => navigate('/dashboard')}
          className="btn-secondary px-6"
        >
          Back to Dashboard
        </button>
      )}
    </div>
  );
}
