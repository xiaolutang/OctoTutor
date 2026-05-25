'use client';

import { ConversationProvider } from '@/contexts/conversation-context';
import { ChatLayout } from '@/components/chat-layout';
import { ConversationSidebar } from '@/components/conversation-sidebar';
import { ChatUI } from '@/components/chat-ui';

export default function ChatPage() {
  return (
    <ConversationProvider>
      <ChatLayout
        sidebar={<ConversationSidebar />}
      >
        <ChatUI />
      </ChatLayout>
    </ConversationProvider>
  );
}
