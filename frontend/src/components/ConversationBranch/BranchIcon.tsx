export function BranchIcon({ size = 16 }: { size?: number }) {
  return (
    <svg aria-hidden="true" width={size} height={size} viewBox="0 0 24 24"
      fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="M2 12h7c2 0 3-1 4-2l7-7m-6 0h6v6M14 15l6 6m0-6v6h-6" />
    </svg>
  );
}

export const conversationBranchesEnabled = process.env.NEXT_PUBLIC_CONVERSATION_BRANCHES !== 'false';
