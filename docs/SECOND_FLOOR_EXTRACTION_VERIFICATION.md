# Second-floor photo extraction verification

The original 992 × 440 photograph was re-extracted without manual edits or
model weights. The review reference was the user's corrected report (revision
146). Compared with main at `ef2e70c`, using the repository's pixel-space
scorer (opening interval IoU ≥ 0.5, with direction and offset checks):

| Second-floor measure | Before | After |
| --- | ---: | ---: |
| Reference doors matched | 3/5 | 5/5 |
| Door proposals | 4 | 6 |
| Reference windows matched | 9/9 | 9/9 |
| Window proposals | 12 | 9 |
| Wall centerline precision | 89.2% | 100.0% |
| Wall centerline recall | 96.1% | 97.8% |

The additional bathroom door is visible on the source but absent from the
corrected export, so the scorer counts it as unmatched. The two recovered
reference doors are the left side of the central recess and the Mamad entrance.
Some windows remain proposals, and matching does not establish exact
dimensions. A small lower partition and a few seams still differ from the
correction. The room graph also differs; these results do not establish room
area accuracy.

Three cold extraction runs took 2.32–2.42 seconds in this workspace (worker
only, not upload or rendering). The farmhouse worker output matched the
baseline byte for byte. The garden retained its matched door and window counts
(2/5 and 1/5); window proposals decreased from 9 to 6. Its wall recall stayed
70.0%, with precision moving from 66.1% to 65.5%. It is still an open case.

The focused opening, ink, and reconstruction tests passed. The full API suite
had 358 passes, one skip and six failures; all six failures were reproduced on
the previous commit (envelope inference and room reconstruction).
