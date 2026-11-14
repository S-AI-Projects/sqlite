# Hints

## 1. Match each DNA nucleotide to its RNA complement

The instructions give the complete mapping:

| DNA | RNA |
|---|---|
| `A` | `U` |
| `C` | `G` |
| `G` | `C` |
| `T` | `A` |

## 2. Preserve the sequence

Transcribe each nucleotide from the original DNA strand in its existing
position. The empty strand has no nucleotides to replace, so its result is
empty. If using a sequence of replacements, make sure a newly inserted
nucleotide is not accidentally processed again.

## 3. Compare with the selected examples

| Test description | DNA input | Expected RNA |
|---|---|---|
| Empty RNA sequence | `""` | `""` |
| RNA complement of cytosine is guanine | `"C"` | `"G"` |
| RNA complement of guanine is cytosine | `"G"` | `"C"` |
| RNA complement of thymine is adenine | `"T"` | `"A"` |
| RNA complement of adenine is uracil | `"A"` | `"U"` |
| RNA complement | `"ACGTGGTCTTAA"` | `"UGCACCAGAAUU"` |

For the longer strand, applying the mapping one position at a time gives
`A C G T G G T C T T A A` → `U G C A C C A G A A U U`.

## Contract boundary

The selected cases and instructions specify uppercase DNA nucleotides `A`,
`C`, `G`, and `T`. They do not specify how to handle invalid symbols, lowercase
letters, whitespace, or other inputs outside that contract. Do not infer a
required rejection, normalization, or pass-through behavior for those inputs.
