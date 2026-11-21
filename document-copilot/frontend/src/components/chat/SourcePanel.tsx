import { X } from 'lucide-react'
import { useEffect } from 'react'

import ExcerptView from '@/components/chat/ExcerptView'
import { Button } from '@/components/ui/button'
import { formatFilingDate, sourceLabel, type Source } from '@/lib/citations'

interface Props {
  source: Source
  highlight: string | null // a figure from the answer to mark in the passage
  onClose: () => void
}

// The passage a citation points at, exactly as it is stored, so an analyst can check the
// claim against the filing text in one click.
export default function SourcePanel({ source, highlight, onClose }: Props) {
  // Escape closes the panel.
  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [onClose])

  return (
    <aside
      aria-label={`Source ${source.marker}`}
      className="fixed inset-0 z-20 flex flex-col bg-background md:static md:z-auto md:w-[28rem] md:shrink-0 md:border-l lg:w-[36rem]"
    >
      <header className="flex items-start justify-between gap-2 border-b p-4">
        <div className="min-w-0">
          <p className="text-xs text-muted-foreground">Source {source.marker}</p>
          <h2 className="font-medium">{sourceLabel(source)}</h2>
        </div>
        <Button variant="ghost" size="icon-sm" onClick={onClose} aria-label="Close source">
          <X />
        </Button>
      </header>

      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 border-b p-4 text-sm">
        <dt className="text-muted-foreground">Filed</dt>
        <dd>{formatFilingDate(source.filing_date)}</dd>
        <dt className="text-muted-foreground">Section</dt>
        <dd>{source.section ?? 'Not available'}</dd>
        <dt className="text-muted-foreground">Accession</dt>
        <dd className="break-all">{source.accession_number}</dd>
      </dl>

      <div className="flex-1 overflow-y-auto p-4">
        <p className="mb-2 text-xs text-muted-foreground">
          Exact text of the passage cited{highlight && <> · <mark className="rounded bg-primary/25 px-1">{highlight}</mark> is marked below</>}
        </p>
        <ExcerptView excerpt={source.excerpt} highlight={highlight} />
      </div>
    </aside>
  )
}
