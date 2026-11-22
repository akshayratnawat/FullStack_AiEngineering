import { useOutletContext } from 'react-router-dom'

// What ChatLayout hands to the page shown beside the sidebar.
export interface ChatOutletContext {
  // Reloads the sidebar list, for after a reply when the thread's title or order changed.
  refreshThreads: () => Promise<void>
  // Opens a new chat, optionally asking `question` in it straight away.
  startChat: (question?: string) => Promise<void>
  // For questions the user TYPES: true when it may be asked. For a visitor and a question that
  // needs a live answer it returns false after opening the "by invitation" notice, so callers
  // just stop. Picking a sample question does not go through this: it never needs the notice.
  requestAsk: (question: string) => boolean
}

export function useChatOutlet() {
  return useOutletContext<ChatOutletContext>()
}
