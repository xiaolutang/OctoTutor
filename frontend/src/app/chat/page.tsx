'use client';

import { ConversationProvider } from '@/contexts/conversation-context';
import { ChatLayout } from '@/components/chat-layout';
import { ConversationSidebar } from '@/components/conversation-sidebar';
import { ChatUI } from '@/components/chat-ui';
import { useChatStream } from '@/chat/use-chat-stream';

function ChatPageInner() {
  const { isStreaming } = useChatStream();

  return (
    <ChatLayout
      sidebar={<ConversationSidebar isStreaming={isStreaming} />}
    >
      <ChatUI />
    </ChatLayout>
  );
}

export default function ChatPage() {
  return (
    <ConversationProvider>
      <ChatPageInner />
    </ConversationProvider>
  );
}
