import { cn } from '@/utils/cn';
import type { MemberRole } from '@/types';
import { ROLE_LABELS, ROLE_COLORS } from '@/types';

interface BadgeProps {
  label: string;
  className?: string;
}

export function Badge({ label, className }: BadgeProps) {
  return (
    <span className={cn('badge bg-gray-100 text-gray-600', className)}>
      {label}
    </span>
  );
}

export function RoleBadge({ role }: { role: MemberRole }) {
  return (
    <span className={cn('badge', ROLE_COLORS[role])}>
      {ROLE_LABELS[role]}
    </span>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    active:     'bg-emerald-50 text-emerald-600 border border-emerald-100',
    pending:    'bg-amber-50 text-amber-600 border border-amber-100',
    suspended:  'bg-red-50 text-red-500 border border-red-100',
    inactive:   'bg-gray-100 text-gray-500',
  };

  return (
    <span className={cn('badge', styles[status] ?? styles.inactive)}>
      {status}
    </span>
  );
}
