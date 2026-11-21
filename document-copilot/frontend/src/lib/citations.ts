// The sources behind an answer. The backend streams them as one `data-citations` part
// after the answer text and saves the same part, so a reloaded thread shows them too.

import type { UIMessage } from 'ai'

export interface Source {
  marker: number // the [n] in the answer text
  chunk_id: string
  ticker: string
  form: string
  fiscal_year: number
  filing_date: string
  accession_number: string
  section: string | null
  excerpt: string // the exact text of the cited passage
}

const CITATIONS_PART = 'data-citations'
// Marks an assistant message that only explains why no answer was given.
const FAILED_PART = 'data-turn-failed'

function isSource(value: unknown): value is Source {
  if (typeof value !== 'object' || value === null) return false
  const v = value as Record<string, unknown>
  return (
    typeof v.marker === 'number' &&
    typeof v.ticker === 'string' &&
    typeof v.form === 'string' &&
    typeof v.fiscal_year === 'number' &&
    typeof v.excerpt === 'string'
  )
}

export function sourcesOf(message: UIMessage): Source[] {
  const part = message.parts.find((candidate) => candidate.type === CITATIONS_PART)
  if (!part || !('data' in part) || !Array.isArray(part.data)) return []
  return part.data.filter(isSource)
}

export function isFailedReply(message: UIMessage): boolean {
  return message.parts.some((part) => part.type === FAILED_PART)
}

// "AAPL 10-K FY2025": which company's filing, in the short form used on chips.
export function sourceLabel(source: Source): string {
  return `${source.ticker} ${source.form} FY${source.fiscal_year}`
}

export function formatFilingDate(isoDate: string): string {
  const date = new Date(`${isoDate}T00:00:00`)
  if (Number.isNaN(date.getTime())) return isoDate
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(date)
}

export type Segment =
  | { kind: 'text'; text: string }
  | { kind: 'marker'; marker: number; start: number } // start: where the [n] begins in the text

// Splits answer text into plain text and its [n] markers, so each marker can be a button.
export function splitMarkers(text: string): Segment[] {
  const segments: Segment[] = []
  let last = 0
  for (const match of text.matchAll(/\[(\d{1,3})\]/g)) {
    if (match.index > last) segments.push({ kind: 'text', text: text.slice(last, match.index) })
    segments.push({ kind: 'marker', marker: Number(match[1]), start: match.index })
    last = match.index + match[0].length
  }
  if (last < text.length) segments.push({ kind: 'text', text: text.slice(last) })
  return segments
}

// The figure written just before a marker, such as "$77.7 billion" or "39%", or null when the
// marker follows words (it backs the whole statement). The panel highlights it in the passage.
export function figureBefore(textBeforeMarker: string): string | null {
  const match = /(\$?\s?\d[\d,]*(?:\.\d+)?\)?\s?(?:%|billion|million|thousand)?)\s*$/i.exec(textBeforeMarker)
  return match ? match[1].trim() : null
}
