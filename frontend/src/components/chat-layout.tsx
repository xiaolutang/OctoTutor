'use client';

import { Toaster } from '@/components/ui/sonner';

interface ChatLayoutProps {
  sidebar: React.ReactNode;
  children: React.ReactNode;
}

export function ChatLayout({ sidebar, children }: ChatLayoutProps) {
  return (
    <div className="flex h-[calc(100vh-3.5rem)]">
      <aside className="w-64 shrink-0 border-r bg-background">{sidebar}</aside>
      <main className="flex-1 overflow-hidden">{children}</main>
      <Toaster />
    </div>
  );
}
