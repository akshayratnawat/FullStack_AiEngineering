import { ArrowUpRight } from 'lucide-react'

import { EXAMPLES } from '@/lib/examples'

interface Props {
  onPick: (question: string) => void
  disabled?: boolean // a chat is being created or a reply is on its way
}

// Questions to pick instead of typing. Clicking one asks it straight away.
export default function ExampleQuestions({ onPick, disabled = false }: Props) {
  // One row per question: a heading, and the question in small text underneath, cut to one line.
  return (
    <ul className="divide-y overflow-hidden rounded-xl border bg-background" aria-label="Example questions">
      {EXAMPLES.map((example) => (
        <li key={example.title}>
          <button
            type="button"
            disabled={disabled}
            onClick={() => onPick(example.question)}
            className="group flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-accent focus-visible:bg-accent focus-visible:outline-none disabled:pointer-events-none disabled:opacity-50"
          >
            <span className="min-w-0 flex-1">
              <span className="block text-sm font-medium">{example.title}</span>
              <span className="mt-0.5 block truncate text-sm text-muted-foreground">{example.question}</span>
            </span>
            <ArrowUpRight
              className="size-4 shrink-0 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100"
              aria-hidden
            />
          </button>
        </li>
      ))}
    </ul>
  )
}
