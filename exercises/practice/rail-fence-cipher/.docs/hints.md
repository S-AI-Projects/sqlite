# Hints

The exercise's contract is a zig-zag traversal of a fixed number of rails.
The maintained reference represents that traversal as a JSON matrix and keeps
the path positions separate from the characters. Read the selected cases as a
decision table:

| Case | Operation | Input message | Rails | Required result |
| --- | --- | --- | ---: | --- |
| encode with two rails | encode | `XOXOXOXOXOXOXOXOXO` | 2 | `XXXXXXXXXOOOOOOOOO` |
| encode with three rails | encode | `WEAREDISCOVEREDFLEEATONCE` | 3 | `WECRLTEERDSOEEFEAOCAIVDEN` |
| encode with ending in the middle | encode | `EXERCISES` | 4 | `ESXIEECSR` |
| decode with three rails | decode | `TEITELHDVLSNHDTISEIIEA` | 3 | `THEDEVILISINTHEDETAILS` |
| decode with five rails | decode | `EIEXMSMESAORIWSCE` | 5 | `EXERCISMISAWESOME` |
| decode with six rails | decode | `133714114238148966225439541018335470986172518171757571896261` | 6 | `112358132134558914423337761098715972584418167651094617711286` |

For two rails the path alternates between the top and bottom row, which
explains the two runs in the first output. With three or more rails, continue
down to the last rail and back up; an ending in the middle (as in
`EXERCISES`, four rails) still follows the same path and must not be padded.
Decode by filling the same path positions in row order, then reading the path
back in zig-zag order.

The specification does not define behavior for an empty message, one rail,
zero rails, more rails than characters, or an unknown operation. Those inputs
are outside this exercise's tested contract; do not add an exception or
coercion rule based on them.
