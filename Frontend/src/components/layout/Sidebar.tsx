import { NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { cn } from '@/utils/cn';

const NAV_ITEMS = [
  {
    to: '/dashboard',
    label: 'Dashboard',
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
          d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
      </svg>
    ),
  },
  {
    to: '/organizations',
    label: 'Organizations',
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
          d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
      </svg>
    ),
  },
];

// Repositories nav item is rendered separately so it can show
// the currently-active org's repo link from the URL pattern.
const REPO_NAV = {
  pattern: '/organizations/',
  label: 'Repositories',
  icon: (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
        d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
    </svg>
  ),
};


// ── Logo mark ─────────────────────────────────────────────────────────────────

function LogoMark() {
  return (
    <div className="flex items-center gap-2.5">
      <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-forge-400 to-forge-600 flex items-center justify-center shadow-lg shadow-forge-950/50">
        <svg className="w-4 h-4 text-white" viewBox="0 0 24 24" fill="currentColor">
          <path d="M13 10V3L4 14h7v7l9-11h-7z" />
        </svg>
      </div>
      <span className="font-bold text-white text-sm tracking-wide">ForgeAI</span>
    </div>
  );
}

// ── Sidebar ───────────────────────────────────────────────────────────────────

export function Sidebar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  // Extract orgId from the current URL if we're inside an org context
  const currentPath = window.location.pathname;
  const orgMatch = currentPath.match(/\/organizations\/(\d+)/);
  const activeOrgId = orgMatch ? orgMatch[1] : null;

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <aside className="w-60 flex-shrink-0 flex flex-col h-screen bg-surface-800 border-r border-white/5 px-3 py-5">
      {/* Logo */}
      <div className="px-2 mb-8">
        <LogoMark />
      </div>

      {/* Navigation */}
      <nav className="flex-1 flex flex-col gap-1">
        <p className="px-3 text-[10px] font-semibold text-violet-500 uppercase tracking-widest mb-1">
          Platform
        </p>
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              cn('sidebar-item', isActive && 'active')
            }
          >
            {item.icon}
            {item.label}
          </NavLink>
        ))}

        {/* Repositories — only visible when inside an org context */}
        {activeOrgId && (
          <NavLink
            to={`/organizations/${activeOrgId}/repositories`}
            className={({ isActive }) =>
              cn('sidebar-item', isActive && 'active')
            }
          >
            {REPO_NAV.icon}
            {REPO_NAV.label}
          </NavLink>
        )}

        {/* Always-visible Repositories shortcut when no org in URL */}
        {!activeOrgId && (
          <button
            onClick={() => navigate('/dashboard')}
            className={cn('sidebar-item text-left')}
          >
            {REPO_NAV.icon}
            Repositories
          </button>
        )}
      </nav>

      {/* User footer */}
      <div className="mt-4 pt-4 border-t border-white/8">
        <div className="flex items-center gap-3 px-2 py-2 rounded-xl hover:bg-white/5 transition-colors group">
          {/* Avatar */}
          <div className="w-8 h-8 rounded-full bg-gradient-to-br from-forge-400 to-purple-500 flex items-center justify-center text-white text-xs font-bold flex-shrink-0">
            {user?.name?.charAt(0).toUpperCase() ?? '?'}
          </div>

          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-white truncate">{user?.name}</p>
            <p className="text-xs text-violet-400 truncate">{user?.email}</p>
          </div>

          <button
            onClick={handleLogout}
            title="Sign out"
            className="opacity-0 group-hover:opacity-100 text-violet-400 hover:text-red-400 transition-all"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
            </svg>
          </button>
        </div>
      </div>
    </aside>
  );
}

