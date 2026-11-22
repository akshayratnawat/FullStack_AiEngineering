// Questions a visitor can pick instead of typing, each asked exactly as written.
//
// Every question here MUST have a stored answer in backend/app/demo/answers.json: picking one
// plays that answer (research steps, text, sources) without a model call, so anyone may do it,
// including a visitor without live access. The backend test `test_every_example_has_a_recording`
// fails when a question here has no stored answer. Check each answer against the filings before
// adding it: it is the first thing every visitor sees.

export interface ExampleQuestion {
  title: string // the heading on the row
  question: string // what is actually asked (shown small under the heading)
}

export const EXAMPLES: ExampleQuestion[] = [
  {
    title: 'Apple iPhone sales',
    question: "What were Apple's iPhone net sales in fiscal 2024?",
  },
  {
    title: 'AWS operating income',
    question: 'What was AWS operating income in 2024?',
  },
  {
    title: 'Microsoft total revenue',
    question: "What was Microsoft's total revenue in fiscal 2024?",
  },
  {
    title: 'Supplier concentration',
    question:
      'For Apple and NVIDIA, what do the filings say about supplier concentration or dependence on third-party manufacturing, and did the wording become more or less urgent over time?',
  },
  {
    title: 'AI infrastructure spending',
    question:
      'Compare capital expenditures and purchase commitments for Microsoft, Alphabet, Amazon, and NVIDIA. What do the filings imply about the scale and timing of AI/cloud infrastructure investment?',
  },
]

// The backend matches a stored question ignoring case, spacing and a trailing question mark;
// this does the same, so a visitor who TYPES one of these questions is treated like one who
// picked it (it replays; the "by invitation" notice is only for questions needing a live answer).
function normalize(question: string): string {
  return question.replace(/\s+/g, ' ').trim().replace(/\?+$/, '').trim().toLowerCase()
}

const STORED = new Set(EXAMPLES.map((example) => normalize(example.question)))

export function hasStoredAnswer(question: string): boolean {
  return STORED.has(normalize(question))
}
