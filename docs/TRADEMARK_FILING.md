# Trademark filing prep

Working notes for registering the marks named in
[TRADEMARK.md](https://github.com/Flux-Frontiers/gutenberg_kg/blob/main/TRADEMARK.md).
Nothing here is legal advice, and nothing here has been filed yet. The point of
the page is that the facts a USPTO application asks for are scattered across
git history and App Store Connect, and reconstructing them under deadline is
worse than writing them down now.

## Why bother

The practical reason is Apple. If a copycat build of The Knowledge Press shows
up on the App Store, the remedy runs through Apple's
[Content Dispute](https://www.apple.com/legal/internet-services/itunes/appstorenotices/)
form, and that form is built around intellectual-property claims. A registered
mark makes the claim close to mechanical. A copyright argument resting on the
terms in `app/LICENSE` is winnable but slow, and slow is the whole problem when
a clone is live and taking your installs.

Registration also converts the common-law rights that already exist into
something enforceable outside the geography where the mark has actually been
used, and puts later applicants on constructive notice.

## The marks, in filing order

Priority runs top to bottom. If the budget only covers one, file the first.

| Mark | Class | Basis | Notes |
|---|---|---|---|
| The Knowledge Press | 9 (downloadable software) | 1(b) intent-to-use | The App Store name. Not yet in commerce, so 1(b); a Statement of Use follows once the app ships. |
| The Knowledge Press | 42 (SaaS) | 1(b) intent-to-use | Only if a hosted offering is ever likely. Skip otherwise; each class costs a separate fee. |
| GutenbergKG | 9 | 1(a) in use | Public on GitHub since 2026-03-30 and released under DOI, which is a use-in-commerce argument. Cleaner mark than the one above -- coined, not descriptive. |
| App icon | 9 | 1(a) or 1(b) | A design mark, filed separately from any word mark. Weakest priority of the four. |

## The owner is not a choice

Flux-Frontiers is a trade name, not an LLC or a corporation. It does not
exist as a legal person, so it cannot own a registration, and the applicant
must be the natural person: **Eric G. Suchanek, PhD, an individual**, with
"DBA Flux-Frontiers" as the optional trade-name line.

This matters more than the usual "get the paperwork right" way. An application
filed in the name of an entity that does not exist is void *ab initio* -- not
refused and amendable, but void. The fee is forfeited and the filing-date
priority is lost, because correcting the applicant would amount to
substituting a different party. It is one of the few defects the USPTO will
not let you cure. Everything else on this page can be fixed in prosecution;
this cannot.

The same reasoning applies to the Apple Developer account, which is enrolled
to the individual, so the App Store seller name will be the personal legal
name rather than "Flux-Frontiers". Showing a trade name there requires an
Organization enrollment, which requires a real legal entity and a D-U-N-S
number.

If an LLC is formed later, the path is an assignment from the individual to
the entity, recorded with the USPTO, plus an Apple App Transfer and
re-enrollment in the Small Business Program, which is per-account and does not
travel with a transferred app. All routine. The owner name on the original
application is the only part that has to be right the first time.

Worth doing alongside the filing: most states require a fictitious-name or DBA
registration to trade under a name that is not your own. That filing is what
makes "DBA Flux-Frontiers" on the application a documented fact rather than an
assertion.

## The descriptiveness problem

"The Knowledge Press" is suggestive at best and arguably descriptive of
software that indexes books, which is the ground an examiner refuses on under
Section 2(e)(1). Three ways that can go:

1. Accepted on the Principal Register as suggestive. The "Press" half is a
   metaphor here -- nothing is printed -- and metaphor is what separates
   suggestive from descriptive.
2. Refused, then accepted on the Supplemental Register, which still deters and
   still supports an Apple dispute, and can move to the Principal Register
   after five years of continuous use.
3. Refused outright, in which case `GutenbergKG` carries the weight. It is a
   coined term and the far stronger mark.

Filing `GutenbergKG` alongside rather than after is the cheap hedge.

## Facts an application will ask for

| Field | Value |
|---|---|
| Owner | **Eric G. Suchanek, PhD, an individual, DBA Flux-Frontiers.** Settled, not a choice -- see [The owner is not a choice](#the-owner-is-not-a-choice). |
| First use anywhere, GutenbergKG | 2026-03-30, first appearance in the public repository |
| First use in commerce, GutenbergKG | Tie to a tagged, DOI-archived release. `v1.0.0` was tagged 2026-05-04. |
| First use anywhere, The Knowledge Press | 2026-05-04, `30b969b` |
| First use in commerce, The Knowledge Press | None yet. App Store availability date will set it. |
| Goods and services, class 9 | Downloadable software for building, indexing, searching, and querying knowledge graphs over digitized text corpora |
| Specimen, class 9 | The App Store product page once live. A GitHub README is usually refused as a specimen for downloadable software; a store listing is not. |

## Sequence

1. Search first. [TESS](https://tmsearch.uspto.gov/) for both word marks, plus
   a plain web search for unregistered users. A conflicting common-law user
   beats a later registrant.
2. File the state or county DBA for Flux-Frontiers, if not already on record.
3. File TEAS Plus for `GutenbergKG`, 1(a), class 9, with a release specimen.
4. File TEAS Plus for `The Knowledge Press`, 1(b), class 9.
5. Ship the app. Availability date becomes first use in commerce.
6. File the Statement of Use for the 1(b) application within six months of the
   Notice of Allowance, extendable.

Step 1 is worth twenty minutes with an attorney; the rest is form filling.
The owner name, per above, is no longer an open question.

## Meanwhile

`TRADEMARK.md` and the copyright notices in every source file are doing real
work already. Common-law rights attach through use, not registration, and a
published policy is evidence of both the claim and its scope. Registration
strengthens what exists; it does not create it.
