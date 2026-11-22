import { useChatOutlet } from '@/components/chat/chat-context'

// Questions an analyst might open with, written the way the filings can answer them.
// Each one is asked as written, so it names the company and the years it needs.
const EXAMPLES = [
  {
    title: 'Apple revenue mix',
    question:
      "Across Apple's 2021–2025 10-Ks, how did the revenue mix between iPhone, Services, Mac, iPad, and Wearables change, and which category appears to have contributed most to any mix shift?",
  },
  {
    title: 'AWS vs the rest of Amazon',
    question:
      'For Amazon, compare AWS operating income and margin against North America and International from 2021–2025. In which years did AWS appear to fund losses or weaker profitability elsewhere?',
  },
  {
    title: 'Microsoft and cloud capacity',
    question:
      "Across Microsoft's 2021–2025 filings, what changed in the way the company describes Azure, AI infrastructure, and cloud capacity constraints?",
  },
  {
    title: 'Supplier concentration',
    question:
      'For Apple and NVIDIA, what do the filings say about supplier concentration or dependence on third-party manufacturing, and did the wording become more or less urgent over time?',
  },
]

// Shown at "/" beside the sidebar, before any conversation is open.
export default function ChatHomePage() {
  const { startChat } = useChatOutlet()

  return (
    <div className="flex h-full flex-col items-center justify-center gap-6 p-6 text-center">
      <div className="flex flex-col gap-2">
        <h2 className="text-2xl font-semibold">Document Copilot</h2>
        <p className="text-muted-foreground">
          Ask about the 10-K filings of Apple, Microsoft, NVIDIA, Amazon and Alphabet. Every figure
          comes with the passage it was taken from.
        </p>
      </div>

      <div className="flex w-full max-w-2xl flex-col gap-2 text-left">
        <p className="text-sm text-muted-foreground">Try a question</p>
        <ul className="grid gap-2 sm:grid-cols-2">
          {EXAMPLES.map((example) => (
            <li key={example.title}>
              <button
                type="button"
                onClick={() => void startChat(example.question)}
                className="h-full w-full rounded-lg border bg-background p-3 text-left text-sm hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring"
              >
                <span className="block font-medium">{example.title}</span>
                <span className="mt-1 line-clamp-3 block text-muted-foreground">{example.question}</span>
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
