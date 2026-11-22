import { ChevronLeft, ChevronRight, ExternalLink, X } from 'lucide-react'
import { useEffect, useRef } from 'react'

import ExcerptView from '@/components/chat/ExcerptView'
import { Button } from '@/components/ui/button'
import { edgarFilingsUrl } from '@/lib/answer'
import { formatFilingDate, sourceLabel, type Source } from '@/lib/citations'

interface Props {
  source: Source
  highlight: string | null // a figure from the answer to mark in the passage
  position: number // where this source is among the answer's sources, from 0
  total: number
  onStep: (delta: number) => void // -1 for the previous source, 1 for the next
  onClose: () => void
}

// The passage a citation points at, exactly as it is stored, so an analyst can check the
// claim against the filing text in one click.
export default function SourcePanel({ source, highlight, position, total, onStep, onClose }: Props) {
  const body = useRef<HTMLDivElement>(null) // the scrolling area
  const passage = useRef<HTMLDivElement>(null) // just the passage, so the label's own <mark> is not found

  // Escape closes the panel; the arrow keys step between sources unless the user is typing.
  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') return onClose()
      const target = event.target
      const typing =
        target instanceof HTMLElement && (target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName))
      if (typing) return
      if (event.key === 'ArrowLeft') onStep(-1)
      if (event.key === 'ArrowRight') onStep(1)
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [onClose, onStep])

  // Bring the highlighted figure into view: a long passage or table may hide it below the fold.
  // A new source starts at the top.
  useEffect(() => {
    const mark = passage.current?.querySelector('mark')
    if (mark) mark.scrollIntoView({ block: 'center', inline: 'center' })
    else body.current?.scrollTo({ top: 0 })
  }, [source, highlight])

  return (
    <aside
      aria-label={`Source ${source.marker}`}
      className="fixed inset-0 z-20 flex flex-col bg-background md:static md:z-auto md:w-[28rem] md:shrink-0 md:border-l lg:w-[36rem]"
    >
      <header className="flex items-start justify-between gap-2 border-b p-4">
        <div className="min-w-0">
          <p className="text-xs text-muted-foreground">
            Source {source.marker}
            {total > 1 && <> · {position + 1} of {total}</>}
          </p>
          <h2 className="font-medium">{sourceLabel(source)}</h2>
        </div>
        <div className="flex shrink-0 gap-1">
          {total > 1 && (
            <>
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={() => onStep(-1)}
                disabled={position <= 0}
                aria-label="Previous source"
              >
                <ChevronLeft />
              </Button>
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={() => onStep(1)}
                disabled={position >= total - 1}
                aria-label="Next source"
              >
                <ChevronRight />
              </Button>
            </>
          )}
          <Button variant="ghost" size="icon-sm" onClick={onClose} aria-label="Close source">
            <X />
          </Button>
        </div>
      </header>

      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 border-b p-4 text-sm">
        <dt className="text-muted-foreground">Filed</dt>
        <dd>{formatFilingDate(source.filing_date)}</dd>
        <dt className="text-muted-foreground">Section</dt>
        <dd>{source.section ?? 'Not available'}</dd>
        <dt className="text-muted-foreground">Accession</dt>
        <dd className="break-all">{source.accession_number}</dd>
        <dt className="text-muted-foreground">Original</dt>
        <dd>
          {/* Opens the company's filing list on SEC EDGAR; the accession number above picks the filing. */}
          <a
            href={edgarFilingsUrl(source)}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 underline underline-offset-4"
          >
            {source.ticker} filings on SEC EDGAR <ExternalLink className="size-3" />
          </a>
        </dd>
      </dl>

      <div ref={body} className="flex-1 overflow-y-auto p-4">
        <p className="mb-2 text-xs text-muted-foreground">
          Exact text of the passage cited
          {highlight && (
            <>
              {' · '}
              <mark className="rounded bg-primary/25 px-1">{highlight}</mark> is marked below
            </>
          )}
        </p>
        <div ref={passage}>
          <ExcerptView excerpt={source.excerpt} highlight={highlight} />
        </div>
      </div>
    </aside>
  )
}
