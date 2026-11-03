import React from 'react';
import { cn } from '@/utils/cn';

interface CardProps {
  children: React.ReactNode;
  className?: string;
  padding?: 'none' | 'sm' | 'md' | 'lg';
}

export function Card({ children, className, padding = 'md' }: CardProps) {
  const paddings = {
    none: '',
    sm: 'p-4',
    md: 'p-6',
    lg: 'p-8',
  };

  return (
    <div className={cn('glass-card', paddings[padding], className)}>
      {children}
    </div>
  );
}

interface CardHeaderProps {
  title: string;
  description?: string;
  action?: React.ReactNode;
}

export function CardHeader({ title, description, action }: CardHeaderProps) {
  return (
    <div className="flex items-start justify-between gap-4 mb-6">
      <div>
        <h2 className="text-lg font-semibold text-white">{title}</h2>
        {description && (
          <p className="text-sm text-surface-400 mt-0.5">{description}</p>
        )}
      </div>
      {action && <div className="flex-shrink-0">{action}</div>}
    </div>
  );
}

// ── Stat card ─────────────────────────────────────────────────────────────────

interface StatCardProps {
  label: string;
  value: string | number;
  icon: React.ReactNode;
  trend?: { value: string; up: boolean };
  color?: string;
}

export function StatCard({ label, value, icon, trend, color = 'text-forge-400' }: StatCardProps) {
  return (
    <div className="stat-card group hover:border-forge-500/40 transition-all duration-200">
      <div className="flex items-center justify-between mb-3">
        <span className="text-[11px] font-semibold text-surface-400 uppercase tracking-wider">
          {label}
        </span>
        <span className={cn('p-2 rounded-xl bg-surface-800 border border-white/5', color)}>
          {icon}
        </span>
      </div>
      <div className="text-3xl font-bold text-white tracking-tight">{value}</div>
      {trend && (
        <div className={cn('text-xs mt-2 flex items-center gap-1 font-medium', trend.up ? 'text-emerald-400' : 'text-red-400')}>
          <svg className={cn('w-3 h-3', !trend.up && 'rotate-180')} fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M5.293 9.707a1 1 0 010-1.414l4-4a1 1 0 011.414 0l4 4a1 1 0 01-1.414 1.414L11 7.414V15a1 1 0 11-2 0V7.414L6.707 9.707a1 1 0 01-1.414 0z" clipRule="evenodd" />
          </svg>
          {trend.value}
        </div>
      )}
    </div>
  );
}
