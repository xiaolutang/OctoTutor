import { RouteGuard } from '@/components/route-guard'
import { ChatUI } from '@/components/chat-ui'

export default function ChatPage() {
  return (
    <RouteGuard>
      <div className="container mx-auto flex h-[calc(100vh-3.5rem)] flex-col px-4">
        <ChatUI />
      </div>
    </RouteGuard>
  )
}
