# Hints

## General

Given two lists `A` and `B`, determine their relationship:
- `equal`: Both lists have identical elements in the exact same order.
- `sublist`: List `A` is contained within list `B` as a contiguous sub-sequence.
- `superlist`: List `B` is contained within list `A` as a contiguous sub-sequence.
- `unequal`: Neither list is a contiguous sub-sequence of the other.

---

## Decision Table & Contract Cases

### 1. Decision Table

The relationship between list $A$ (`list_one`) and list $B$ (`list_two`) can be modeled systematically based on element contents and sequence lengths:

| Condition | List A (`list_one`) | List B (`list_two`) | Result | Contract Rationale |
| :--- | :--- | :--- | :--- | :--- |
| **Both Empty** | `[]` | `[]` | `equal` | Empty lists are identical in length ($0$) and elements. |
| **A Empty, B Non-Empty** | `[]` | `[1]` or `[1, 2, 3]` | `sublist` | The empty sequence is trivially a contiguous sublist of any list. |
| **A Non-Empty, B Empty** | `[1]` or `[1, 2, 3]` | `[]` | `superlist` | Any non-empty list trivially contains the empty sequence as a sublist. |
| **Identical Elements** | `[1, 2, 3]` | `[1, 2, 3]` | `equal` | Equal length and identical pairwise values in identical order. |
| **Contiguous Slice ($|A| < |B|$)** | `[2, 3]` | `[1, 2, 3, 4]` | `sublist` | $A$ appears contiguously at index 1 of $B$. |
| **Contiguous Slice ($|A| > |B|$)** | `[1, 2, 3, 4]` | `[2, 3]` | `superlist` | $B$ appears contiguously at index 1 of $A$. |
| **Disjoint / Interleaved** | `[1, 3]` | `[1, 2, 3]` | `unequal` | $A$ elements are present in $B$, but they are not **contiguous**. |
| **Permuted Order** | `[1, 2, 3]` | `[3, 2, 1]` | `unequal` | Elements match, but order differs. |

---

### 2. Contiguous Subsequence Matching

A fundamental distinction in this exercise is that a sublist is **not** an arbitrary mathematical subset or sparse subsequence. List $A$ must appear in list $B$ as an **unbroken, consecutive sequence of values**:

- **Valid Sublist**:
  - $A = [2, 3, 4]$ within $B = [1, 2, 3, 4, 5]$ matches contiguously at index 1.
- **Invalid Subsequence (Unequal)**:
  - $A = [1, 3]$ within $B = [1, 2, 3]$ is **not** a sublist because element `2` intervenes between `1` and `3`.

In SQLite, checking contiguous windows can be implemented via:
1. **Recursive Sliding Windows**:
   - A `WITH RECURSIVE` CTE sliding an index $i$ from $0$ up to $|B| - |A|$.
   - Unwrapping slice elements with `json_each(list_two)` where `key BETWEEN i AND i + len`.
   - Rebuilding candidate slices with `JSON_GROUP_ARRAY(value)` and checking equality via `JSON(list_one) = JSON(subl)`.
2. **Normalized Delimited Sequences**:
   - Transforming array numbers into uniformly delimited strings and performing exact substring containment.

---

### 3. Delimiter Pitfalls in String / JSON Matching

When comparing JSON arrays, naive string matching (e.g. `LIKE` or `INSTR`) without explicit element boundaries leads to severe false positives:

- **False Substring Collisions**:
  - `[1]` appearing inside `[10]`:
    - Searching for `"[1]"` inside `"[10, 1]"` or `"[1, 0, 1]"` inside `"[10, 1]"` will falsely match text characters if boundaries are ignored.
  - `[1, 2]` appearing inside `[1, 22]`:
    - Text search for `'1, 2'` inside `'[1, 22]'` partially matches prefix `'1, 2'`, producing false sublist classifications.
- **Robust Solutions in SQLite**:
  - **Structured JSON Unwrapping with `json_each()`**:
    - Treat elements as individual typed values rather than raw character substrings.
    - Extract element tokens by index:
      ```sql
      SELECT j.value
      FROM json_each(list_two) j
      WHERE j.key BETWEEN i AND i + len;
      ```
    - Use `JSON()` comparison to guarantee semantic correctness.
  - **Explicit Element Enclosure**:
    - If string concatenation is employed, every number must be isolated with unambiguous delimiters (e.g., `,1,` vs `,10,`) to prevent substring collisions across numerical prefixes.
