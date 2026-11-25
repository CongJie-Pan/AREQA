import React from 'react';

/** Project mark: a stacked tray (two lid lines over a box), drawn like a lucide icon. */
export function ProjectIcon({ size = 18, ...props }: React.SVGProps<SVGSVGElement> & { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8}
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="M7 3.5h10" />
      <path d="M5 7h14" />
      <rect x="3.5" y="10.5" width="17" height="10" rx="2.5" />
      <path d="M9.5 14.5h5" />
    </svg>
  );
}
