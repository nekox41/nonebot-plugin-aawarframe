# Unified item identities (v0.24.0)

Issue #9 introduces SQLite-backed identity columns while preserving the existing
in-memory GRQ/RapidFuzz API.

## Database

- `items`: one row per verified game item, `id=item_path` (unique);
  nullable `wm_slug` is **unique** and is assigned only on an exact,
  verified game reference. `riven_key` is indexed and may be shared by
  multiple weapon variants.
- `aliases`: user aliases with `FOREIGN KEY item_id REFERENCES items(id)`;
  `UNIQUE(item_id,normalized_name)`. Legacy `item_aliases` entries migrate
  once and are then removed.
- `market_products`: Market-only products with no unique verified game
  identity. These remain searchable using the Market index but **never**
  masquerade as game items. `market_aliases` stores their separate names.
- `item_overrides`, `settings`, `catalog_meta`: retained independently of
  seeded data. `catalog_meta.market_signature` prevents duplicate Market
  writes across restarts.
- Wiki `wiki_pages`/`wiki_keys` remain in the separate `wiki.sqlite3` and
  are not game item identities; realtime worldstate/orders remain TTL caches.

A read-only report for unmatched products is available via
`GameResourceQuery.market_match_report()`; it includes totals grouped by
`missing_game_ref`, `unmatched_game_ref`, `ambiguous_game_ref` and a
bounded list of examples.

## Initialization / migration

A previously used `registry.sqlite3` receives an immutable
`registry.pre-items-v2.sqlite3` backup before first normalized import.
Imported game data is updated in place; user aliases, settings and overrides
are kept. All changes use SQLite transactions so validation failures do not
switch to a partially populated new catalogue. New releases include the
normalized tables in their offline Core archive.

## Riven and Market rules

- MK1, base and Prime weapon variants keep **different** item IDs and may
  share `riven_key`. Family membership is resolved on dataset import; the
  `数值` command reads the persisted family instead of inferring it each time.
- **Updated product requirement (Nov 19, 2026):** all weapon Riven
  calculations use the common disposition **1.2** from the bundled Riven rules.
  The former per-variant `omegaAttenuation` requirement was withdrawn.
- A normal weapon name can intentionally resolve to a Prime product using
  existing explicit alias projection rules; such fallback does **not** assign
  the Prime product's `wm_slug` to the normal weapon's game item.
- Source Market IDs without a trustworthy game path are isolated and
  audited, not silently matched via fuzzy names.

## Performance expectations

Common GRQ item, Riven and Market lookups continue to use prebuilt in-memory
indices. One DB read is used to enumerate a Riven family; only catalog
initialization and source changes rebuild data. Identical Market source
signatures produce no catalog rewrite across restarts.
