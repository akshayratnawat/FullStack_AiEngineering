// Helpers for taking an answer out of the app: the text to copy, and where to find the filing.

import { formatFilingDate, sourceLabel, type Source } from '@/lib/citations'

// The answer with its [n] markers kept, followed by a numbered list of what each one points at,
// so pasted into an email or a note it still says where every figure came from.
export function answerWithFootnotes(text: string, sources: Source[]): string {
  if (sources.length === 0) return text
  const notes = [...sources]
    .sort((a, b) => a.marker - b.marker)
    .map((source) => {
      const section = source.section ? `, ${source.section}` : ''
      return `[${source.marker}] ${sourceLabel(source)}${section} (filed ${formatFilingDate(source.filing_date)}, accession ${source.accession_number})`
    })
  return `${text.trimEnd()}\n\nSources:\n${notes.join('\n')}`
}

// SEC EDGAR's list of a company's 10-K filings. We store the ticker and the accession number but
// not the company's EDGAR number, so this opens the company's filing list rather than the one
// document; the accession number shown in the panel identifies the filing in that list.
export function edgarFilingsUrl(source: Source): string {
  const params = new URLSearchParams({
    action: 'getcompany',
    CIK: source.ticker,
    type: source.form,
    dateb: '',
    owner: 'include',
    count: '40',
  })
  return `https://www.sec.gov/cgi-bin/browse-edgar?${params.toString()}`
}
