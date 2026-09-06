# Demo script

Build Spec Section 12. Under three minutes. Record after the mint batch has
finished, never during it.

**Voice:** direct, confident, unadorned. Short sentences. No corporate register,
no hype vocabulary, no em dashes.

---

## Before you record

- [ ] Mint batch finished hours ago. `ORACLE.MINT_LOG` is populated.
- [ ] Three asset identifiers spot-checked in Solana Explorer from a browser.
- [ ] Warehouse resumed and warm, so the first click does not wait on a cold start.
- [ ] Second browser window already open on Solana Explorer, devnet selected.
- [ ] `sql/99_acceptance_checks.sql` run. Gate reads BUILD ACCEPTED.
- [ ] The Wall opened once already, so the first differential privacy query
      has warmed the privacy engine. It is slower than an ordinary aggregate
      because it is doing real work, and a cold one on camera looks broken.
- [ ] Tab 01 sampled onto a pair with a wide evasion gap. Do not reveal it yet.
- [ ] Nothing on screen shows a credential, a key path, or a terminal with `.env` open.

---

## 0:00 to 0:20 — Tab 01, two cards

Open **cold on the choice**. Do not explain the project first.

> Two organisations. One of them is real. Take a second and pick the one you
> would give to.
>
> Ninety-six million dollars was reported lost in the United States alone in
> 2024 to exactly this. That is the FBI's figure, from January.

Let the pause sit. The viewer should actually try.

## 0:20 to 0:45 — Tab 01, reveal and C01-1

Click a card.

> Meaning similarity, zero point nine four. Spelling similarity, zero point
> five one.
>
> That gap is the whole project. The impersonator kept the meaning and changed
> the spelling on purpose, which is precisely what string matching is built to
> miss. Both of those numbers are computed in SQL, inside the warehouse, with
> no data leaving it.

## 0:45 to 1:05 — Tab 03, hex map

Rotate the map once. Point at a red spike.

> Every delivery, indexed to a hexagonal grid. Height is value, colour is
> whether the geometry makes sense.
>
> This one claims to have landed outside any operating footprint the
> organisation has.

## 1:05 to 1:25 — Tab 04, Sankey

> Pledged, dispatched, delivered, unaccounted. The red band is the one that
> matters.
>
> The attrition here is tuned against a published figure, not chosen to look
> dramatic. The World Food Programme reported 590 trucks moved and 371
> collected inside Gaza. That ratio is the calibration anchor.

## 1:25 to 2:05 — Tab 05, The Wall

**The centrepiece. Give it the time.** Narrow the filters live, one at a time,
and let the viewer watch the three cards diverge.

> Everything so far has been this system finding things. Now watch it refuse.
>
> One question, three objects holding identical facts. Broad, and all three
> agree. Narrow it. Narrow it again. Four people, and the middle card refuses
> outright while the right-hand card hands back a number that is pure noise
> and never mentions it.
>
> Both are protecting the same four people. Only one of them tells you so.
>
> Every accountability project has the same unsolved problem. To prove aid
> reached people you have to publish data about those people. This is the part
> where the tool protects them from me, from you, and from itself.

If there is time, scroll to the differencing sweep: two questions the floor
answers happily, subtracted, and twelve people fall out. Then the same pair
through the budget, where thirty runs landed anywhere between minus 27 and
plus 51.

## 2:05 to 2:30 — Tab 06, The Receipt

Copy an asset identifier. Paste it into the second window on Solana Explorer.

> Do not trust this application. Take an identifier and check it yourself.
>
> That receipt exists whether or not this project does. And here, where the
> lines separate, no receipt was written at all. That absence is a finding, not
> a gap in the demo.

## 2:30 to 2:50 — Tab 09, Where A Dollar Lands

Close warm.

> Every organisation on this tab is real, from a public filing list, and
> cleared every check.
>
> The point was never to catch people. It was to make giving legible.

## 2:50 to 3:00 — Tab 10, Method And Honesty

> The impersonators and the beneficiary records are generated, and every one of
> them is labelled in the data, not just on the screen. The organisations are
> real. The receipts are on devnet.

End there. Do not add a summary.

---

## Lines not to say

- Never call any entity fraudulent, criminal, or a scam. The interface does not,
  and neither should the narration. "Needs a second look" is the ceiling.
- Never imply an individual delivery event is real. The aggregate is calibrated;
  the events are modelled.
- Never say "anonymised" about either policy. Differential privacy is not
  anonymisation and conflating them is the error this tab exists to correct.
- Never call the cohort floor differential privacy. They are two policies on
  two objects, and the whole tab is the difference between them.
- Do not claim the budget stops the differencing attack outright. It breaks a
  single attempt; the limit is set above the cost of grinding through it, and
  the tab says so.
- Never claim a receipt proves delivery. It proves a claim was recorded.

## If something breaks on camera

- **pydeck renders blank.** External Offerings Terms are not accepted. Do not
  debug on camera; the tab falls back to a flat scatter automatically. Keep
  narrating the geography.
- **A query hangs.** The warehouse suspended. Cut, resume it, re-record the
  segment. Do not wait on screen.
- **Explorer is slow.** Say so plainly and move on. The tab reads a local
  mirror, so nothing else stalls.
