import { figureBefore, sourceLabel, splitMarkers, type Source } from '@/lib/citations'
import { cn } from '@/lib/utils'

interface Props {
  text: string
  sources: Source[]
  selectedMarker: number | null
  // `figure` is the number written just before the marker, so the panel can highlight it.
  onSelect: (marker: number, figure: string | null) => void
}

// The answer text with each [n] marker shown as a small superscript number right after the thing
// it backs. Clicking it opens the source. A marker with no matching source (an old message, or a
// stray number) stays plain text.
export default function AnswerText({ text, sources, selectedMarker, onSelect }: Props) {
  return (
    <>
      {splitMarkers(text).map((segment, index) => {
        if (segment.kind === 'text') return segment.text
        const source = sources.find((candidate) => candidate.marker === segment.marker)
        if (!source) return `[${segment.marker}]`
        return (
          <sup key={index} className="mx-px">
            <button
              type="button"
              onClick={() => onSelect(segment.marker, figureBefore(text.slice(0, segment.start)))}
              title={sourceLabel(source)}
              aria-label={`Source ${segment.marker}: ${sourceLabel(source)}`}
              className={cn(
                'rounded px-1 text-[0.7rem] font-semibold leading-none text-primary',
                'bg-primary/10 hover:bg-primary/20 focus-visible:outline-2 focus-visible:outline-ring',
                selectedMarker === segment.marker && 'bg-primary text-primary-foreground hover:bg-primary',
              )}
            >
              {segment.marker}
            </button>
          </sup>
        )
      })}
    </>
  )
}
