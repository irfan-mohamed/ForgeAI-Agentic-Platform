import React from 'react';
import { Sidebar } from './Sidebar';

interface PageLayoutProps {
  children: React.ReactNode;
  fullBleed?: boolean;
}

export function PageLayout({ children, fullBleed = false }: PageLayoutProps) {
  return (
    <div className="flex h-screen overflow-hidden bg-surface-950">
      <Sidebar />
      <main className="flex-1 overflow-y-auto canvas-bg min-w-0">
        {fullBleed ? (
          children
        ) : (
          <div className="p-8 max-w-7xl mx-auto animate-fade-in">{children}</div>
        )}
      </main>
    </div>
  );
}

// ── Page header used inside page components ───────────────────────────────────

interface PageHeaderProps {
  title: string;
  subtitle?: string;
  action?: React.ReactNode;
}

export function PageHeader({ title, subtitle, action }: PageHeaderProps) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8">
      <div>
        <h1 className="text-2xl font-bold text-white tracking-tight">{title}</h1>
        {subtitle && (
          <p className="text-surface-400 mt-1 text-sm">{subtitle}</p>
        )}
      </div>
      {action && <div className="flex items-center gap-3">{action}</div>}
    </div>
  );
}
