import { useOutletContext } from 'react-router-dom'

// What ChatLayout hands to the page shown beside the sidebar.
export interface ChatOutletContext {
  // Reloads the sidebar list, for after a reply when the thread's title or order changed.
  refreshThreads: () => Promise<void>
}

export function useChatOutlet() {
  return useOutletContext<ChatOutletContext>()
}
