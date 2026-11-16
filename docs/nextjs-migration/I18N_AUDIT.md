# Bilingual audit

## Coverage

| Measure | Result |
| --- | --- |
| Keys in `messages/en.json` | 505 |
| Keys in `messages/zh.json` | 505 |
| Keys present in one language only | 0 |
| Empty strings standing in for a translation | 0 |
| Interpolation placeholders differing between languages | 0 |
| Literal `t("…")` keys in source that do not resolve in both | 0 |

Checked by `tests/unit/i18n.test.ts`, which scans `src/` for literal keys,
resolves each against its file's namespace, and separately asserts every value
of the dynamic key families (event states, signal states, volatility states,
filing change kinds, benchmark-unavailable reasons, peer-reference reasons,
evidence-scope statuses, Ask error codes).

## Behaviour

| Requirement | How it is met | Covered by |
| --- | --- | --- |
| Chinese is the default | `defaultLocale: "zh"` with `localePrefix: "always"` | `i18n.spec.ts` |
| Switching keeps the ticker and page context | the switcher re-navigates the same resolved route in the other locale | `i18n.spec.ts` |
| Language survives navigation | locale-aware `Link` keeps the prefix on every internal link | `i18n.spec.ts` |
| Language survives a reload | the switcher writes a `LENS_LOCALE` cookie; a bare path is negotiated from it | `i18n.spec.ts` |
| One language state on desktop and phone | one switcher component, one cookie, no per-page storage | — |
| Correct language on the first server render | `setRequestLocale` + `<html lang>` rendered server-side | `i18n.spec.ts` asserts the raw HTML |
| Titles, meta and `hreflang` follow the language | per-locale `generateMetadata` with `alternates.languages` | verified on the preview |
| No hydration mismatch | all locale decisions are server-side; nothing reads `localStorage` during render | clean console in E2E |
| Legacy `.html` links keep working | 308 to the unprefixed path, then negotiated | `legacy-urls.spec.ts` |

## Localised

Navigation, hero, search and its empty and ambiguous states, directory and
pagination, company snapshot, the three-part brief labels, financial cards and
their definitions and method notes, performance controls, metrics, risk note,
coverage note, chart legend, chart alt text and caption, volatility card,
disclosure-signal card, filings module including change kinds and reaction
wording, all eight event states, the Ask form and every error code, overview,
research, glossary, earnings, the boundary page, footer, accessibility labels.

## Deliberately not translated

| Kept as published | Why |
| --- | --- |
| Tickers | an identifier |
| Official company names | the registrant's own name |
| Quoted filing passages | a translated quotation is not a quotation; marked `lang="en"` |
| Headlines and excerpts | the publisher's wording, in the publisher's language; `lang` is set from the feed's `title_language` |
| us-gaap concept tags | a translated `NetIncomeLoss` is not a us-gaap tag |
| Accession numbers, CIK, URLs | identifiers |
| Model-generated reasons on the signal card | generated in English by the scorer; translating would make the wording unverifiable against the run |
| An AI answer | shown in the language it was generated in; asking again generates one in the other language, and a mismatch is labelled rather than relabelled |

Chinese readers get an explanation beside untranslated evidence, not a
substitute for it.

## Known gaps

- `profile.summary_zh` and `category_zh` come from the engine. Where it supplies
  none, the English text is shown marked `lang="en"` rather than
  machine-translated. The brief does the same with `text_zh`.
- The engine's `warnings[]` are English strings; they are displayed verbatim.
- Event `status_label` and `tier_label` are bilingual in the feed itself, so
  their Chinese comes from the engine, not from these catalogues.
