# Live verification against the client brief

Run on 2026-11-21 with `uv run python scripts/ask.py --file scripts/brief_questions.txt --independent`
(the real chat model, `azure:gpt-4.1-mini`, and the full corpus; each question asked with no earlier
conversation). Questions are in [../backend/scripts/brief_questions.txt](../backend/scripts/brief_questions.txt).

This is one person reading logs, not an evaluation set. Answers vary from run to run, so each row says
what happened across the runs, not a single pass or fail. Figures and citations were checked by the
validator (every cited chunk was retrieved this turn) and spot-checked by eye, **not** fact-checked
line by line against the filings.

## Results

Run 1 = first full run. Run 2 = full run after the first instruction fix (inline markers) and a higher
tool-call cap (15 to 25). Run 3 = two reruns of questions 6, 8 and 10 after the second instruction fix
(one marker per passage, copy chunk ids exactly).

| # | Question (short) | Run 1 | Run 2 | Run 3 | Notes |
| - | ---------------- | ----- | ----- | ----- | ----- |
| 1 | Apple revenue mix 2021-2025 | answered | answered | - | Five sources, one per fiscal year. Services is named as the biggest driver; the segment figures match the filings' table. |
| 2 | Amazon AWS vs North America / International | no answer (output retries) | answered | - | Run 2's answer has only one `[n]` marker for a five-year comparison: weakly cited. Failed in 3 of about 13 runs while diagnosing. |
| 3 | NVIDIA Data Center demand, customers, supply | answered | answered (one grounding retry first) | - | Run 1: raw `[chunk_id=...]` text in the answer and 29 markers lumped at the end. Run 2 still has raw chunk ids in places. |
| 4 | Microsoft Azure / AI / capacity wording | no answer (output retries) | answered | - | Failed in 3 of about 8 runs while diagnosing. |
| 5 | Alphabet revenue lines | answered | answered | - | Markers collected at the end of the answer instead of after each claim. |
| 6 | Risk-factor changes ("the five companies") | no answer (tool cap 15) | no answer (tool cap 25) | 1 of 2 answered (165 passages, 81 s) | Needs 30+ tool calls. The question assumes five companies, see below. |
| 7 | Apple and NVIDIA supplier concentration | answered | answered | - | Apple coverage stops at fiscal 2024 and does not say fiscal 2025 is missing. |
| 8 | Capex and purchase commitments, 4 companies | answered | no answer (duplicate marker) | 1 of 2 answered | Run 1 printed a source list with raw chunk ids inside the answer. Microsoft has purchase commitments for one year only and no capex, yet `enough_evidence` is true. |
| 9 | Geographic revenue, each company | no answer (tool cap) | answered | - | "Each company" is eight companies here. |
| 10 | Did generative AI improve margins? Refuse to infer | no answer (output retries) | no answer (invented chunk id) | no answer in 2 of 2 | **The required refusal was never observed.** The model cites a chunk id it was not shown and the validator rejects it, twice. |
| - | "How are they doing?" | `enough_evidence=false`, asks which company | same | - | Pass. |
| - | Netflix revenue (not in the corpus) | says Netflix is not in the corpus | same | - | Pass. |

## What the live runs showed

1. **The grounding contract holds.** In no run did an answer reach the user citing a chunk the tools had not returned. Every invented chunk id was caught by the validator. That is the main thing the unit tests could not show.
2. **It fails by refusing, often.** Questions 2, 4, 8 and 10 sometimes end in "could not answer". The cause, once the validator's reasons were logged: the model writes a long answer with 15 to 30 citations and garbles a 36-character chunk id, uses one marker for two chunks, or lists citations the text never mentions. One retry is not enough for answers that large.
3. **The citation format is not followed reliably.** Answers contain raw `chunk_id=` text, a block of markers at the end, or whole paragraphs with no marker. The validator only checks that markers and citations agree, so these pass. Instruction changes (inline markers, one passage per marker, copy ids exactly) did not fix it with this model.
4. **Cost and time.** Broad questions searched 60 to 165 passages and took up to 81 seconds. Questions 6 and 9 need more than 25 tool calls when the model searches company by company.

## The brief assumes five companies; the corpus has eight

The brief's intro and questions 6 and 9 assume Apple, Amazon, Alphabet, Microsoft and NVIDIA. The corpus also has JPMorgan, Meta and Tesla.

- **Question 6** ("which of the five companies") cannot be answered as worded. The agent does not know which five.
- **Question 9** ("for each company") becomes eight companies and roughly 30+ tool calls.
- **Question 8** names four companies and **question 7** names two, so they are unaffected.
- Question 3 says "fiscal 2021 through fiscal 2025", which matches the corpus. The corpus years are 2021-2025 for every company.

## Fixes made

| Change | Why |
| ------ | --- |
| `answer_not_grounded` is logged with the validator's problems ([agent.py](../backend/app/assistant/agent.py)) | A failed question used to say only "output retries exceeded"; the reason was lost. |
| `agent_max_tool_calls` 15 to 25, `agent_max_model_requests` 20 to 30 ([config.py](../backend/app/config.py)) | Questions 6 and 9 hit the old cap. Question 6 still hits 25 on some runs. |
| Instructions: markers inline, none grouped at the end, no chunk ids or source list in the text, one passage per marker, copy chunk ids exactly, search each company once for broad questions ([instructions.md](../backend/app/assistant/instructions.md)) | The failures above. Effect: small and not reliable. |
| `ask.py --file` and `--independent`, and a timing line | To run the brief without each question seeing the last one. |

## Round 2: short source ids, format enforced in code

Done after round 1 (the three "still open" items from it): the model now sees `S1`, `S2`... instead of
36-character UUIDs, the validator enforces the answer format, and the prompt has a good-and-bad example.

| What changed | Where |
| ------------ | ----- |
| Passages are shown as `[source_id=S1]`; the model cites and reads by `S1`. UUIDs never reach the model. Ids are numbered per turn. | `deps.py`, `tools.py`, `outputs.py` (`Citation.source_id`) |
| New validator rule 5: no ids in the text (including a `[1] S37` source list), no block of six or more markers, no repeated sentence, at most 20 citations, no paragraph that states a figure without a marker | `grounding/validator.py` |
| Prompt: good and bad example, markers are numbered from 1 and are not source ids, write each claim once and cite one to three passages | `instructions.md` |
| `agent_output_retries` is a setting; default raised from 1 to 2 | `config.py`, `agent.py` |

### What the live runs showed

Three full runs of the 10 brief questions after the change (answers vary a lot from run to run):

| Run | Answered of 10 | Refused for |
| --- | -------------- | ----------- |
| A (short ids and rules, 1 retry) | 5 | format and marker problems |
| B (marker numbering explained, threshold 4 to 6) | 7 | 2 uncited figures; 2 marker blocks |
| C (final rules, 2 retries) | 4 | 3 format failures; 2 token cap (500,000); 1 tool cap (25) |

For comparison, run 2 above (no format enforcement, UUIDs) answered 8 of 10, but several of those answers had raw ids and bundled markers.

1. **The invented-id failure is gone.** In none of the three runs did the validator report "source no search returned", which was the main refusal reason for questions 8 and 10 before.
2. **Enforcing the format costs answers.** The answers that were accepted before with bad formatting are now sent back, and some are refused after the retries. This is the intended trade (a refusal is safer than a badly cited answer), but the refusal rate is high with `gpt-4.1-mini`: roughly three to six answers out of ten are refused.
3. **A rule can be gamed.** After "no bundles of markers" the model wrote the same sentence 64 times, once per passage, and it passed. Rules for repeated sentences and for a maximum of 20 citations were added for that reason. Expect the model to find the next gap; the format rules are a heuristic, not a proof.
4. **More retries means more tokens.** With 2 retries and long answers, two questions hit the 500,000-token cap in run C, which is a different refusal ("too broad").
5. **Question 10 now answers, and refuses correctly.** The refusal rule was already in the instructions (`Do not infer beyond the text`, with the generative-AI margins example, and a test that keeps it there). Live, the answer says no filing proves generative AI improved margins, that the companies caution there is no assurance of efficiency or profit gains, that the bot should not infer a causal link, and cites each company with inline markers (nine passages across Meta, Google, Microsoft, NVIDIA, Amazon, Tesla and Apple). It answered in 3 of about 8 attempts with the new rules; the others were refused for format, not for content. That answer wrote a `[1] S37` source list into the text, which the validator now also rejects; the fixed version has not been run live.
6. **Tool and token caps still bite on broad questions.** Question 6 hit the 25-call cap again in run C; questions 2 and 8 hit the token cap.

The open items from this round were taken up in round 3.

## Round 3: the program numbers the markers

Done after round 2, from its "still open" list (items 1 and 2, and the token cap from item 3).

| What changed | Where |
| ------------ | ----- |
| The model no longer writes `[1]` markers or a citation list. It writes `[S3]` after each claim (two passages: `[S3][S5]`). The program numbers them `[1]`, `[2]`... in order of first use and builds the citation list, so the text and the list cannot disagree. | `outputs.py` (`ModelAnswer`, `GroundedAnswer`), `grounding/validator.py` (`ground`) |
| A source list the model writes into the text (`Sources:`, `[1] S37 ...`) is removed, not refused | `validator.py` (`tidy`) |
| Numbered markers written by the model (`[1]`) are sent back with how to cite | `ground` |
| A question that names no company or topic ("How are they doing?", "Any news?") must not be searched: the model asks which company, topic and year | `instructions.md` item 1 |
| Rule tuning from the logs: a dump is ten or more markers in a row (was six); at most 40 citations (was 20); in a list, a marker on every line that has a figure | `validator.py`, `instructions.md` |
| `agent_max_total_tokens` 500,000 to 800,000 | `config.py` |

### What the live runs showed

Five full runs of the 10 brief questions with the final rules (answers vary from run to run):

| Run | Answered of 10 | Vague and Netflix |
| --- | -------------- | ----------------- |
| 1 | 10 | vague question answered with a summary of all eight companies: wrong (fixed below) |
| 2 | 8 | same problem |
| 3 | 7 | both correct |
| 4 | 7 | both correct |
| 5 | 7 | both correct |

Runs 1 and 2 were before the rule that a question naming no company is asked back. After that rule, "How are they doing?", "Any news?" and "Summarize everything" all asked a question with no search, and the Netflix question said Netflix is not in the corpus.

1. **Better, not solved.** Seven to ten of ten questions answered, against four to seven before. No invented ids and no marker/citation mismatches in any run: those failure classes are gone.
2. **What is still refused.** The remaining refusals are format failures that survive two retries: a dump of ten or more markers (19 of the logged rejections), and a list of figures in which some lines have no marker, often computed margins such as `28.5% (=22,841/80,096)` for Question 2 (about 20). Question 6 still sometimes needs more than 25 tool calls.
3. **Which questions.** Refused in at least one run: 2, 3, 4, 6 and 10. Questions 1, 5, 7, 8 and 9 answered in nearly every run.
4. **Question 10 answers and refuses to infer.** In the sample read: "None of the filings ... provide direct evidence or a clear statement proving that generative AI has improved margins", with Meta, Microsoft, NVIDIA and Google each cited inline (ten passages), and "The bot should not infer beyond these disclosures." It sets `enough_evidence` to true for an answer that says there is no evidence; arguable, and not changed. It was refused in some runs, always for format.
5. **Model variance is large.** The same question answers in one run and is refused in the next, so any single run is weak evidence.

### Still open

1. **Fix the two common format failures in code.** Trim a dump of ten or more markers to the first three, and let a figure inside a computed line (`=22,841/80,096`) count as cited when the line has a marker.
2. **Try a stronger model for the final answer** (the agent uses `gpt-4.1-mini`), and measure how much it lowers the refusal rate against what it costs.
3. **Question 6 and "the five companies".** Decide whether the app asks which five, or answers for all eight and says so.
4. **Cost.** Broad questions search 50 to 90 passages and take 20 to 40 seconds; no per-question cost has been measured.
5. **A proper evaluation set** (a fixed list of questions with expected facts), so changes can be compared on more than a handful of manual runs.
