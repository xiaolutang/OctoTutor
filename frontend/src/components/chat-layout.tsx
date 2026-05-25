'use client';

import { SidebarProvider } from '@/components/ui/sidebar';
import { Toaster } from '@/components/ui/sonner';

interface ChatLayoutProps {
  sidebar: React.ReactNode;
  children: React.ReactNode;
}

export function ChatLayout({ sidebar, children }: ChatLayoutProps) {
  return (
    <SidebarProvider>
      <div className="flex h-full">
        <aside className="w-64 shrink-0 border-r bg-background">{sidebar}</aside>
        <main className="flex-1 overflow-hidden">{children}</main>
      </div>
      <Toaster />
    </SidebarProvider>
  );
}
