// Tiny utility — avoids pulling in the full clsx/tailwind-merge stack.
export function cn(...classes: (string | undefined | null | false)[]): string {
  return classes.filter(Boolean).join(' ');
}
