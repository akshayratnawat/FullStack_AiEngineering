import { formatFilingDate, sourceLabel, type Source } from '@/lib/citations'
import { cn } from '@/lib/utils'

interface Props {
  sources: Source[]
  selectedMarker: number | null
  onSelect: (marker: number, figure: string | null) => void
}

// One chip per source under an answer: which company's filing, which form and year, which section.
export default function SourceChips({ sources, selectedMarker, onSelect }: Props) {
  if (sources.length === 0) return null
  return (
    <div className="mt-2 flex flex-wrap gap-1.5 border-t pt-2" aria-label="Sources">
      {sources.map((source) => (
        <button
          key={source.marker}
          type="button"
          onClick={() => onSelect(source.marker, null)}
          title={`Filed ${formatFilingDate(source.filing_date)}`}
          className={cn(
            'flex max-w-full items-center gap-1.5 rounded-md border bg-background px-2 py-1 text-left text-xs',
            'hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring',
            selectedMarker === source.marker && 'border-primary bg-primary/10',
          )}
        >
          <span className="font-semibold">{source.marker}</span>
          <span className="truncate">
            {sourceLabel(source)}
            {source.section && <span className="text-muted-foreground"> · {source.section}</span>}
          </span>
        </button>
      ))}
    </div>
  )
}
