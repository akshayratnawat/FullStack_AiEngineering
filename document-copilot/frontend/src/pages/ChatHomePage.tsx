// Shown at "/" beside the sidebar, before any conversation is open.
export default function ChatHomePage() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center">
      <h2 className="text-2xl font-semibold">Document Copilot</h2>
      <p className="text-muted-foreground">
        Pick a conversation on the left, or start a new chat.
      </p>
    </div>
  )
}
