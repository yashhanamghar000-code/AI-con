# College AI Consultant Dataset v4 — Sparse Verified Fields

- Input rows: 1041
- JSON files generated: 1041
- Unique record IDs: True
- Cutoff data included: No
- Null / unverified placeholders: omitted

## Why this version is smaller
Empty values, nulls, empty arrays/objects, and fields explicitly marked `unverified`, `pending`, or `not_found` are omitted. Only fields with populated values are kept. Every college still receives its own JSON file, even if only identity fields are available.

## Live scraper architecture recommendation
At retrieval time:
1. Search by institute code + canonical institute name.
2. Prefer official college/university pages, CET Cell, NAAC/NBA, NIRF and Maharashtra Fees Regulating Authority.
3. Extract only fields supported by a source.
4. Store each field with source URL, retrieved timestamp, and confidence.
5. Cache results with a TTL and re-crawl stale fields.
6. Keep cutoff data outside this dataset, as requested.

## Official source references
- Maharashtra CET Cell institute list: https://fe2026.mahacet.org/StaticPages/frmInstituteList
- CET Cell institute summary (course details and intake where applicable): https://fe2026.mahacet.org/StaticPages/frmInstituteSummary
- State CET Cell portal: https://cetcell.mahacet.org/

## Integrity note
This pass performs sparse cleanup and merges populated information already available in the uploaded index and previous dataset. It is not a claim that every one of the 1041 colleges was individually re-crawled live. Some fields may remain absent until your live scraper retrieves them.
