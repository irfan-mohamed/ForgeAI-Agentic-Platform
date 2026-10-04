import { Link } from 'react-router-dom';

export function NotFoundPage() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-surface-950">
      <div className="text-center animate-fade-in">
        <p className="text-8xl font-bold text-gradient mb-4">404</p>
        <h1 className="text-2xl font-bold text-white mb-2">Page not found</h1>
        <p className="text-surface-400 mb-8">
          The page you're looking for doesn't exist or has been moved.
        </p>
        <Link
          to="/dashboard"
          className="inline-flex items-center gap-2 px-6 py-3 bg-forge-600 hover:bg-forge-500 text-white font-semibold rounded-xl transition-all"
        >
          ← Back to Dashboard
        </Link>
      </div>
    </div>
  );
}
