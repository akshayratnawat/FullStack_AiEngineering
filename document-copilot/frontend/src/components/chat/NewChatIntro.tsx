import ExampleQuestions from '@/components/chat/ExampleQuestions'

interface Props {
  onPick: (question: string) => void
  disabled?: boolean
}

// What a new, empty chat shows above the message box: what this is, and questions to pick.
export default function NewChatIntro({ onPick, disabled = false }: Props) {
  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-col gap-2 text-center">
        <h2 className="text-2xl font-semibold">Document Copilot</h2>
        <p className="text-muted-foreground">
          Ask about the 10-K filings of big tech companies such as Apple, Microsoft, NVIDIA, etc.
          Every answer is grounded in the actual 10-K documents.
        </p>
      </div>

      <div className="flex flex-col gap-2">
        <p className="px-1 text-sm text-muted-foreground">Try a question, or type your own below</p>
        <ExampleQuestions onPick={onPick} disabled={disabled} />
      </div>
    </div>
  )
}
