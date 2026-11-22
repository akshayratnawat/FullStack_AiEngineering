import type { ReactNode } from 'react'

import { isFigure, matchesFigure, parseExcerpt } from '@/lib/excerpt'
import { cn } from '@/lib/utils'

interface Props {
  excerpt: string
  highlight: string | null // a figure from the answer; the matching numbers in the passage are marked
}

const MARK = 'rounded bg-primary/25 px-0.5 font-semibold ring-1 ring-primary/40'

// A line of prose with each number that matches the highlighted figure marked.
function markedText(text: string, highlight: string | null): ReactNode {
  if (!highlight) return text
  return text.split(/(\d[\d,]*(?:\.\d+)?)/).map((part, index) =>
    index % 2 === 1 && matchesFigure(part, highlight) ? (
      <mark key={index} className={MARK}>
        {part}
      </mark>
    ) : (
      part
    ),
  )
}

// The cited passage with its tables drawn as tables, and the figure the answer quotes marked.
// A wide table scrolls sideways inside its own box instead of wrapping its columns into a mess.
export default function ExcerptView({ excerpt, highlight }: Props) {
  return (
    <div className="flex flex-col gap-3 rounded-md border bg-muted/40 p-3 text-sm leading-relaxed">
      {parseExcerpt(excerpt).map((block, index) => {
        if (block.kind === 'text') return <p key={index}>{markedText(block.text, highlight)}</p>
        return (
          <div key={index} className="overflow-x-auto rounded border bg-background">
            <table className="w-full border-collapse text-xs">
              <thead>
                <tr className="border-b bg-muted/60">
                  {block.header.map((cell, column) => (
                    <th
                      key={column}
                      className={cn('px-2 py-1.5 font-medium whitespace-nowrap', column === 0 ? 'text-left' : 'text-right')}
                    >
                      {cell}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {block.rows.map((row, rowIndex) => (
                  <tr key={rowIndex} className="border-b last:border-b-0">
                    {row.map((cell, column) => (
                      <td
                        key={column}
                        className={cn(
                          'px-2 py-1',
                          column === 0 ? 'min-w-40 text-left' : 'whitespace-nowrap',
                          isFigure(cell) && 'text-right tabular-nums',
                          highlight && column > 0 && matchesFigure(cell, highlight) && MARK,
                        )}
                      >
                        {cell}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      })}
    </div>
  )
}
