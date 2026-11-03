import { cn } from '@/utils/cn';
import type { MemberRole } from '@/types';
import { ROLE_LABELS, ROLE_COLORS } from '@/types';

interface BadgeProps {
  label: string;
  className?: string;
}

export function Badge({ label, className }: BadgeProps) {
  return (
    <span className={cn('badge bg-surface-700/60 text-surface-200 border border-white/10', className)}>
      {label}
    </span>
  );
}

export function RoleBadge({ role }: { role: MemberRole }) {
  return (
    <span className={cn('badge', ROLE_COLORS[role])}>
      {ROLE_LABELS[role] ?? role}
    </span>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    active:     'bg-emerald-500/15 text-emerald-300 border border-emerald-500/30',
    ready:      'bg-emerald-500/15 text-emerald-300 border border-emerald-500/30',
    pending:    'bg-amber-500/15 text-amber-300 border border-amber-500/30',
    syncing:    'bg-blue-500/15 text-blue-300 border border-blue-500/30',
    suspended:  'bg-red-500/15 text-red-300 border border-red-500/30',
    failed:     'bg-red-500/15 text-red-300 border border-red-500/30',
    inactive:   'bg-surface-800 text-surface-400 border border-white/10',
  };

  return (
    <span className={cn('badge capitalize', styles[status] ?? styles.inactive)}>
      {status}
    </span>
  );
}

export function SeverityBadge({ severity }: { severity: string }) {
  const upper = severity.toUpperCase();
  const styles: Record<string, string> = {
    CRITICAL: 'bg-red-500/20 text-red-300 border border-red-500/40',
    HIGH:     'bg-orange-500/20 text-orange-300 border border-orange-500/40',
    MEDIUM:   'bg-amber-500/20 text-amber-300 border border-amber-500/40',
    LOW:      'bg-blue-500/20 text-blue-300 border border-blue-500/40',
    INFO:     'bg-surface-700/60 text-surface-300 border border-white/10',
  };

  return (
    <span className={cn('badge font-mono tracking-wider text-[10px]', styles[upper] ?? styles.INFO)}>
      {upper}
    </span>
  );
}

export function CategoryBadge({ category }: { category: string }) {
  const upper = category.toUpperCase();
  const styles: Record<string, string> = {
    SECURITY:       'bg-purple-500/20 text-purple-300 border border-purple-500/30',
    BUG:            'bg-red-500/20 text-red-300 border border-red-500/30',
    TESTING:        'bg-cyan-500/20 text-cyan-300 border border-cyan-500/30',
    ARCHITECTURE:   'bg-indigo-500/20 text-indigo-300 border border-indigo-500/30',
    MAINTAINABILITY:'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30',
  };

  return (
    <span className={cn('badge text-[10px] tracking-wide font-medium', styles[upper] ?? 'bg-surface-800 text-surface-300 border border-white/10')}>
      {upper}
    </span>
  );
}
