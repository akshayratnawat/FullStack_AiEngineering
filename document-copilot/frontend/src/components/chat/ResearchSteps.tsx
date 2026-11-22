import { Check, ChevronRight, LoaderCircle } from 'lucide-react'

import type { Progress } from '@/lib/progress'
import { cn } from '@/lib/utils'

function StepList({ steps, working }: { steps: string[]; working: boolean }) {
  return (
    <ol className="flex flex-col gap-1">
      {steps.map((step, index) => {
        const current = working && index === steps.length - 1
        return (
          <li key={index} className={cn('flex items-start gap-2', current && 'text-foreground')}>
            {current ? (
              <LoaderCircle className="mt-0.5 size-3.5 shrink-0 animate-spin" aria-hidden />
            ) : (
              <Check className="mt-0.5 size-3.5 shrink-0 text-primary" aria-hidden />
            )}
            <span className="min-w-0 break-words">{step}</span>
          </li>
        )
      })}
    </ol>
  )
}

// What the assistant searched and read to answer. Shown live while it works, so a long question
// is not a silent wait; afterwards folded into one line that opens to show the same steps.
export default function ResearchSteps({ progress }: { progress: Progress }) {
  if (progress.steps.length === 0) return null

  if (!progress.done) {
    return (
      <div role="status" aria-live="polite" className="mb-2 text-xs text-muted-foreground">
        <StepList steps={progress.steps} working />
      </div>
    )
  }

  const count = progress.steps.length
  return (
    <details className="group mb-2 text-xs text-muted-foreground">
      <summary className="flex cursor-pointer list-none items-center gap-1 select-none hover:text-foreground [&::-webkit-details-marker]:hidden">
        <ChevronRight className="size-3.5 transition-transform group-open:rotate-90" aria-hidden />
        How this was answered · {count} {count === 1 ? 'step' : 'steps'}
      </summary>
      <div className="mt-1.5 pl-1">
        <StepList steps={progress.steps} working={false} />
      </div>
    </details>
  )
}
