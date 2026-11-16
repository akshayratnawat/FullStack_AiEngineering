import { Navigate, useParams } from 'react-router-dom'

import ChatThread from '@/components/chat/ChatThread'

export default function ChatThreadPage() {
  const { threadId } = useParams()
  if (!threadId) return <Navigate to="/" replace /> // the route always has one; this narrows the type

  // The key restarts the chat state when the user opens a different thread.
  return <ChatThread key={threadId} threadId={threadId} />
}
