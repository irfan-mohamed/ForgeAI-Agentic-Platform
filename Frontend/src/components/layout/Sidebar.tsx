import { useEffect, useState } from 'react';
import { NavLink, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { organizationsApi } from '@/api/organizations';
import { cn } from '@/utils/cn';
import type { Organization } from '@/types';

function LogoMark() {
  return (
    <div className="flex items-center gap-2.5">
      <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-forge-500 to-forge-700 flex items-center justify-center shadow-lg shadow-forge-900/50 border border-white/10">
        <svg className="w-4 h-4 text-white" viewBox="0 0 24 24" fill="currentColor">
          <path d="M13 10V3L4 14h7v7l9-11h-7z" />
        </svg>
      </div>
      <div>
        <span className="font-bold text-white text-sm tracking-wider">Forge<span className="text-forge-400">AI</span></span>
        <span className="block text-[9px] uppercase tracking-widest text-surface-400 font-mono">Platform</span>
      </div>
    </div>
  );
}

export function Sidebar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [orgs, setOrgs] = useState<Organization[]>([]);
  const [selectedOrgId, setSelectedOrgId] = useState<number | null>(null);

  // Extract orgId from current URL if present: /organizations/123/...
  const orgMatch = location.pathname.match(/\/organizations\/(\d+)/);
  const activeOrgId = orgMatch ? Number(orgMatch[1]) : selectedOrgId;

  useEffect(() => {
    organizationsApi.list()
      .then((res) => {
        setOrgs(res.data);
        if (res.data.length > 0) {
          const matched = location.pathname.match(/\/organizations\/(\d+)/);
          const matchedId = matched ? Number(matched[1]) : null;
          setSelectedOrgId(matchedId ?? res.data[0].id);
        }
      })
      .catch(() => {});
  }, [location.pathname]);

  const handleOrgChange = (newOrgId: number) => {
    setSelectedOrgId(newOrgId);
    // If currently on an org route, switch to the new org's same subpage
    if (orgMatch) {
      const subpath = location.pathname.replace(/\/organizations\/\d+/, '');
      navigate(`/organizations/${newOrgId}${subpath || '/repositories'}`);
    } else {
      navigate(`/organizations/${newOrgId}/repositories`);
    }
  };

  const currentOrg = orgs.find(o => o.id === activeOrgId) ?? orgs[0];
  const orgIdForLinks = activeOrgId ?? currentOrg?.id;

  const navItems = [
    {
      to: '/dashboard',
      label: 'Overview',
      icon: (
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
            d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
        </svg>
      ),
    },
    {
      to: orgIdForLinks ? `/organizations/${orgIdForLinks}/repositories` : '/dashboard',
      label: 'Repositories',
      badge: 'Git Sync',
      icon: (
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
            d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
        </svg>
      ),
    },
    {
      to: orgIdForLinks ? `/organizations/${orgIdForLinks}/ai` : '/dashboard',
      label: 'AI Workspace',
      badge: 'Agent',
      icon: (
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
            d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
        </svg>
      ),
    },
    {
      to: orgIdForLinks ? `/organizations/${orgIdForLinks}/reviews` : '/dashboard',
      label: 'Code Reviews',
      badge: 'PR Analysis',
      icon: (
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
            d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
        </svg>
      ),
    },
    {
      to: orgIdForLinks ? `/organizations/${orgIdForLinks}/tests` : '/dashboard',
      label: 'Test Assistance',
      icon: (
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
            d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" />
        </svg>
      ),
    },
    {
      to: orgIdForLinks ? `/organizations/${orgIdForLinks}/plans` : '/dashboard',
      label: 'Feature Planner',
      badge: 'Graph',
      icon: (
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
            d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7" />
        </svg>
      ),
    },
    {
      to: orgIdForLinks ? `/organizations/${orgIdForLinks}/members` : '/dashboard',
      label: 'Team & Members',
      icon: (
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
            d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" />
        </svg>
      ),
    },
  ];

  return (
    <aside className="w-64 flex-shrink-0 flex flex-col h-screen bg-surface-900 border-r border-white/6 px-3 py-5 select-none">
      {/* Logo */}
      <div className="px-2 mb-6">
        <LogoMark />
      </div>

      {/* Organization Switcher Dropdown */}
      {orgs.length > 0 && (
        <div className="mb-6 px-1">
          <label className="block text-[10px] font-semibold text-surface-500 uppercase tracking-wider mb-1.5 px-1">
            Active Workspace
          </label>
          <div className="relative">
            <select
              value={currentOrg?.id ?? ''}
              onChange={(e) => handleOrgChange(Number(e.target.value))}
              className="w-full appearance-none bg-surface-800 border border-white/10 rounded-xl px-3 py-2 text-xs font-medium text-white focus:outline-none focus:ring-2 focus:ring-forge-500/30 pr-8 cursor-pointer truncate"
            >
              {orgs.map((o) => (
                <option key={o.id} value={o.id} className="bg-surface-800 text-white">
                  {o.name}
                </option>
              ))}
            </select>
            <div className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-surface-400">
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </div>
          </div>
        </div>
      )}

      {/* Navigation */}
      <nav className="flex-1 flex flex-col gap-1 overflow-y-auto pr-1">
        <p className="px-3 text-[10px] font-semibold text-surface-500 uppercase tracking-widest mb-1">
          Engineering Platform
        </p>

        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              cn('sidebar-item group', isActive && 'active')
            }
          >
            <span className="text-surface-400 group-hover:text-forge-300 transition-colors">
              {item.icon}
            </span>
            <span className="flex-1 truncate">{item.label}</span>
            {item.badge && (
              <span className="text-[9px] font-mono uppercase px-1.5 py-0.5 rounded bg-surface-800 text-surface-400 border border-white/5">
                {item.badge}
              </span>
            )}
          </NavLink>
        ))}

        <div className="mt-4 pt-4 border-t border-white/6">
          <button
            onClick={() => navigate('/setup')}
            className="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs text-surface-400 hover:text-white hover:bg-white/5 transition-colors"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            New Organization
          </button>
        </div>
      </nav>

      {/* User profile / Logout footer */}
      <div className="mt-auto pt-4 border-t border-white/6">
        <div className="flex items-center gap-3 px-2 py-2 rounded-xl bg-surface-800/40 border border-white/5 group">
          <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-forge-500 to-purple-600 flex items-center justify-center text-white text-xs font-bold flex-shrink-0 shadow-md shadow-forge-900/40">
            {user?.name?.charAt(0).toUpperCase() ?? 'U'}
          </div>

          <div className="flex-1 min-w-0">
            <p className="text-xs font-semibold text-white truncate">{user?.name || 'Engineer'}</p>
            <p className="text-[11px] text-surface-400 truncate">{user?.email}</p>
          </div>

          <button
            onClick={() => {
              logout();
              navigate('/login');
            }}
            title="Sign out"
            className="w-7 h-7 rounded-lg flex items-center justify-center text-surface-400 hover:text-red-400 hover:bg-red-500/10 transition-colors flex-shrink-0"
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
