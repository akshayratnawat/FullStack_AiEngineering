// A cited passage is plain text with markdown tables in it (one row per line, cells between
// pipes). This splits it into prose lines and tables so the panel can draw real tables.
// Nothing is changed or dropped: every cell and line of the stored text is still shown.

export type Block =
  | { kind: 'text'; text: string }
  | { kind: 'table'; header: string[]; rows: string[][] }

const isTableLine = (line: string) => line.trimStart().startsWith('|')

function cellsOf(line: string): string[] {
  return line
    .trim()
    .replace(/^\|/, '')
    .replace(/\|$/, '')
    .split('|')
    .map((cell) => cell.trim())
}

// The "|-----|-----|" line under a header: it only separates, so it is not drawn.
const isSeparator = (cells: string[]) => cells.every((cell) => /^:?-{2,}:?$/.test(cell))

export function parseExcerpt(excerpt: string): Block[] {
  const blocks: Block[] = []
  let tableLines: string[] = []

  function endTable() {
    const rows = tableLines.map(cellsOf).filter((cells) => !isSeparator(cells))
    tableLines = []
    if (rows.length === 0) return
    const [header, ...body] = rows
    blocks.push({ kind: 'table', header, rows: body })
  }

  for (const line of excerpt.split('\n')) {
    if (isTableLine(line)) {
      tableLines.push(line)
      continue
    }
    endTable()
    if (line.trim()) blocks.push({ kind: 'text', text: line.trim() })
  }
  endTable()
  return blocks
}

// A figure such as "191,973", "39%", "(3)%" or "$1.2": drawn right-aligned so columns line up.
export const isFigure = (cell: string) => /^[($-]*[\d,.]+\)?%?$|^\(\d+\)%$/.test(cell)

function parseFigure(text: string): { value: number; decimals: number; unit: string } | null {
  const match = /(\d[\d,]*(?:\.\d+)?)\)?\s?(%|billion|million|thousand)?/i.exec(text)
  if (!match) return null
  const number = match[1].replace(/,/g, '')
  const decimals = number.includes('.') ? number.split('.')[1].length : 0
  return { value: Number(number), decimals, unit: (match[2] ?? '').toLowerCase() }
}

// True if a number written in the passage is the figure the answer states: the same value, or the
// same value after the usual million/billion conversion (a table in millions against "$201.2 billion").
export function matchesFigure(passageText: string, figure: string): boolean {
  const wanted = parseFigure(figure)
  if (!wanted) return false
  for (const found of passageText.matchAll(/\d[\d,]*(?:\.\d+)?/g)) {
    const value = Number(found[0].replace(/,/g, ''))
    if (value === wanted.value) return true
    if ((wanted.unit === 'billion' || wanted.unit === 'million') && Math.abs(value / 1000 - wanted.value) <= 0.5 * 10 ** -wanted.decimals + 1e-9) {
      return true
    }
  }
  return false
}
