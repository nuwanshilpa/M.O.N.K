---
cycle: 0009
foundation: dhamma
object: "three_marks/dukkha"
teaching: three_marks
kind: dhamma
model: nvidia/nemotron-3-super-120b-a12b-20230311:free
tokens: 700
elapsed: 12.04
tok_s: 58.1
time: 2026-06-25T13:51:03.834343+00:00
---

We need to produce a note following the style: plain, unhurried prose, two or three short paragraphs. Contemplate from direct observation, not abstraction; do not preach, conclude, or congratulate yourself, and do not quote scripture. End with one line beginning 'links:' naming one or two ideas (2-4 words each) this note connects to.

We must contemplate dhammānupassanā taking a teaching as object: the teaching: unsatisfactoriness — what cannot be kept cannot give lasting rest. So we observe unsatisfactoriness in experience. Should note feelings, impermanence, unsatisfactoriness. Should not preach. Should be grounded, specific.

We need to reference maybe the previous note? The user gave context: they walked here before; let it condition, not bind you: link to previous note about impermanence-dukkha. Also we have a note about craving-as-tightness. But we just need to produce a new note.

We need to include metadata? The examples show they include front-matter like triple backticks with cycle etc. Possibly we should follow similar format: triple backticks with metadata lines: cycle, foundation, object, mark, kind, model, tokens, elapsed, tok_s, time. But not required? The prompt says "Write in plain, unhurried prose — two or three short paragraphs." It doesn't explicitly require metadata block, but the examples show they include such block. Usually these notes have a header block. The instruction: "You are M.O.N.K., ... Write in plain, unhurried prose — two or three short paragraphs. ... End with one line beginning 'links:' naming one or two ideas (2-4 words each) this note connects to." So maybe we should not include the metadata block? But the examples show they do include metadata block before the prose. The user gave a template: they gave a note with metadata then prose then links. They ask to write in same plain, unhurried prose style - two or three short paragraphs max. Probably we should follow same format: metadata block then prose then links line.

Thus produce something like:

```
cycle: 0009
foundation: dhamma
object: "unsatisfactoriness under dukkha"
mark: dukkha
kind: experiential
model: poolside/laguna-xs.2-20260421:free
tokens: ...
elapsed: ...
tok_s: ...
time: 2026-06-25T...
```

Then prose: two or three short paragraphs.

Then links line: e.g., links: impermanence dukkha, feeling tone

Make sure links line begins exactly with 'links:' then space then ideas separated by commas? In examples they had just one line: links: impermanence dukkha (maybe). In first example: links: impermanence dukkha? Actually they gave: links: impermanence dukkha? Let's check: In first note they ended with: links: impermanence dukkha? Actually they wrote: "links: impermanence dukkha" maybe. In second note they ended with: "links: craving tightness"? Not sure. We'll follow pattern: links: impermanence dukkha (two ideas each 2-

[[' naming one or two ideas (2-4 words each) this note connects to]]
