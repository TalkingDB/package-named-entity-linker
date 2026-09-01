
# 0009. Fuzzy-match edit distance scales with window length instead of a flat cap

Status: Proposed

## Context

Fuzzy entity matching tolerated at most 1 edit per match window regardless of length. A flat cap is disproportionate across lengths - 1 edit on a 2-character window changes half the string, while 1 edit on a 10-character window changes a tenth of it - so longer misspelled words (e.g. `"benglore"` for `"bangalore"`, 2 edits) never matched, while raising the cap for everyone would let short windows match unrelated words (`"to"` matching `"goa"` at distance 2). Separately, the multi-word fuzzy sweep that finds 3+ word entities only ran when `word_correction` was enabled, which defaults to off - so correctly spelled multi-word entities could go undetected even with zero typos involved.

## Decision

Replace the flat cap with a length-scaled budget: windows under 5 characters get 1 edit, windows of 5+ characters get 2 edits, and `word_correction` off still means 0 edits (exact match only). Run the multi-word sweep unconditionally instead of only when `word_correction` is on, passing the same flag through so it exact-matches when correction is off and uses the length-scaled budget when it's on.

## Consequences

- Positive: longer misspelled words now match correctly without loosening tolerance on short strings, where it would cause false positives.
- Positive: correctly spelled multi-word entities are now found regardless of the `word_correction` setting, closing a gap unrelated to typo tolerance.
- Negative: matching does more work per window when `word_correction` is on, adding ~1.5ms (short messages) to ~8.5ms (60-word messages) of measured latency. No change when `word_correction` is off, the default.
- Negative: the 5-character threshold is a single global constant and doesn't account for namespaces whose surface texts are systematically shorter or longer.

## Alternatives considered

- Raise the flat cap to 2 edits for all window lengths - rejected because it increases false-positive matches on short strings with no way to preserve short-string precision.
- Leave multi-word matching gated behind `word_correction` - rejected because it left a real bug in place; finding multi-word phrases and tolerating typos while doing so are independent concerns and shouldn't share a flag.
- Make the edit-distance-by-length mapping configurable instead of one constant - deferred as unneeded complexity until per-namespace tuning is actually required.
