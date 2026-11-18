# AI-CON Engineering Admissions Consultant --- Improvement & Optimization Plan

**Purpose:** Give this document to a coding agent (Codex, Claude Code,
Cursor, etc.) as the implementation specification for improving the
existing AI-CON project.

**Operating rule:** Modify the existing project incrementally. Do not
replace the architecture, delete datasets, overwrite model artifacts, or
claim a task is complete without running its acceptance tests.

------------------------------------------------------------------------

## 0. Master instructions for the coding agent

### Exact prompt

> You are the senior AI/ML and full-stack engineer responsible for
> improving my existing AI-CON Maharashtra engineering admissions
> counselling system.
>
> First inspect the complete repository, understand its current
> architecture, dependencies, data formats, entry points, tests, and
> runtime flow. Use the existing implementation as the source of truth.
> Do not assume filenames, schemas, feature names, model inputs, or data
> paths that you have not inspected.
>
> Work through this document task by task, in order. Before editing each
> component: 1. Locate the actual implementation and its callers. 2.
> Explain the current behaviour and identify the specific defect with
> code evidence. 3. Create a backup or use version control; never
> destroy existing datasets, indexes, or model artifacts. 4. Implement
> the smallest coherent change that solves the issue. 5. Add or update
> automated tests. 6. Run the relevant tests and report exact commands
> and results. 7. Update this document's completion checklist and
> implementation notes.
>
> Preserve the current technology stack and working features. Do not
> migrate frameworks or rewrite the project from scratch. Do not
> fabricate college data, cutoffs, popularity, placement figures, ROI,
> probabilities, citations, or model metrics. When evidence is missing,
> expose that limitation.
>
> Do not use an LLM to perform deterministic database filtering, cutoff
> arithmetic, institute-code matching, deduplication, or score
> calculations. Use Python/SQL for deterministic operations and use Qwen
> only for language understanding, orchestration decisions where
> appropriate, and evidence-grounded natural-language responses.
>
> Implement one task at a time. Do not proceed past a failing acceptance
> test without documenting the failure and fixing it.

------------------------------------------------------------------------

## 1. Project context and known issues

The project is AI-CON, a Maharashtra engineering admissions
decision-support system. The existing system includes: - Hierarchical
CAP cutoff data, with the latest reported runtime loading 389
institutes. - A college-information dataset and ChromaDB vector index. -
`CollegeInfoAgent` for semantic retrieval and source metadata. -
`CutoffAgent` for exact historical cutoff retrieval. - An orchestrator
and query/college resolution components. - Recommendation and CAP
option-planning components. - Tabular ML artifacts for cutoff rank and
percentile prediction. - A local Qwen/Ollama generation path in the RAG
pipeline. - A web scraper cache / fallback capability in the broader
application.

Known user-visible defects from observed chatbot runs: 1. A request for
30 popular Pune colleges returned only 9 college/branch rows. 2. A
follow-up such as "give me list of 30 colleges" was interpreted as a
request to identify one college. 3. A later query for Pune colleges at
94 percentile returned a single invalid "College of Computer" entity
with no institute code. 4. Different college/branch combinations showed
the same predicted cutoff (about 95.92%). 5. Predicted closing rank was
repeatedly shown as `#1`, which is suspicious and must be traced to the
actual prediction and display pipeline. 6. The result included duplicate
colleges across different branches, while the requested count was
described as colleges. 7. Branch names were truncated or incomplete in
at least one response. 8. The output labelled popularity and ROI without
explaining their source or calculation. 9. Historical cutoff data and
future-year model predictions were displayed together without enough
explanation. 10. Conversation follow-ups did not reliably retain the
student profile and previous result set.

Important distinction: - A college can have multiple eligible branches.
A request for **30 colleges** means 30 unique institutes, not 30 branch
rows. - A request for 30 results does not authorize the system to invent
records. If fewer than 30 match the actual dataset and filters, return
the actual count and explain the shortfall. - "OPEN" must not be blindly
converted into every possible OPEN seat code. Resolve quota/seat type
using the admission rules and ask a clarification only if genuinely
necessary. Preserve the exact category/seat code used for every
retrieved cutoff. - Pune city, Pune district, and nearby locations such
as Alandi/Wagholi must be represented consistently and transparently. Do
not silently mix geographic scopes.

### Exact prompt

> Audit the current AI-CON repository and compare its actual
> implementation with the known defects in Section 1. Produce a concise
> architecture map showing the entry point, query parser, intent router,
> session/context storage, college master data, vector retrieval, cutoff
> retrieval, recommendation engine, ML training and inference, Qwen
> generation, scraper fallback, and response formatting. For each
> defect, identify the responsible file/function and reproduce it with a
> test before changing code. Do not assume the defect is in the model
> until the inference path and displayed result are traced end to end.

------------------------------------------------------------------------

## 2. Task 1 --- Establish a safe baseline and test suite

### Goals

-   Protect current working code, data, indexes and models.
-   Capture reproducible baseline outputs.
-   Build tests before making large changes.

### Exact prompt

> Implement a baseline and regression-test phase for AI-CON.
>
> 1.  Inspect the repository and identify all runtime entry points and
>     test commands.
> 2.  Record Python/runtime versions, dependency versions, configured
>     model name, embedding model, vector-index path, cutoff-data path,
>     college-data path, and model-artifact paths.
> 3.  Verify that all required files and directories exist. Do not
>     silently create empty replacements for missing production data.
> 4.  Add a safe diagnostic command that reports component availability
>     and record counts without exposing secrets.
> 5.  Add fixture-based tests for:
>     -   exact college lookup by institute code;
>     -   exact cutoff lookup by institute, branch, category, year and
>         round;
>     -   multi-college discovery by location and branch;
>     -   a 30-unique-college request;
>     -   follow-up "rank these by ROI" using the preceding shortlist;
>     -   follow-up "show only Pune colleges";
>     -   missing cutoff evidence;
>     -   no matching branch;
>     -   duplicate institute/branch records;
>     -   malformed or absent model predictions.
> 6.  Save representative baseline outputs in a test fixture, excluding
>     personal data and secrets.
> 7.  Add structured logging with request/session correlation IDs.
>
> Acceptance criteria: - Existing startup still works. - Baseline tests
> run using one documented command. - Tests do not depend on live web
> scraping or a live LLM. - No production data or model artifact is
> modified by tests.

------------------------------------------------------------------------

## 3. Task 2 --- Query understanding and intent routing

### Goals

Correctly distinguish: - `college_discovery` - `cutoff_lookup` -
`cutoff_trend` - `college_information` - `college_comparison` -
`roi_ranking` - `popularity_ranking` - `option_form_planning` -
`ml_cutoff_prediction` - `follow_up` - `clarification_required`

Extract structured entities: - exam (MHT-CET/JEE/etc.); - percentile; -
merit rank, if explicitly provided; - category and exact seat/quota
type, if known; - domicile and home-university details when relevant; -
location scope; - preferred branches; - academic year; - CAP round; -
requested number of unique colleges; - ranking objective.

### Exact prompt

> Inspect the current query-intelligence/parser and orchestrator code.
> Implement a typed, validated query representation rather than relying
> on loose keyword matching or a single guessed college name.
>
> Parse this example:
>
> "I have 94 percentile in CET and want colleges in Pune, category OPEN,
> give me a list of the most popular 30 colleges for Computer
> Engineering and related branches."
>
> Expected interpretation: - intent: `college_discovery` with popularity
> ranking; - exam: MHT-CET, only if the application context or explicit
> wording confirms it; - percentile: 94; - category text: OPEN; -
> normalized seat code: unresolved until admission-rule context confirms
> the applicable code; - location: Pune, with the system's documented
> geographic scope; - branches: canonical Computer Engineering, CSE, IT,
> AI & DS, AI & ML and other explicitly configured related branches; -
> requested count: 30 unique institutes; - ranking: popularity, with a
> transparent evidence-based definition.
>
> Parse follow-ups using the active session context. For example, "give
> me 30 colleges" after a shortlist must update the requested count, not
> invoke exact-college resolution.
>
> Use deterministic validation after model-assisted extraction. Reject
> invalid percentiles, unknown categories, malformed years and
> unsupported round numbers. Preserve both the original user wording and
> normalized values.
>
> If a required field is ambiguous, ask one targeted question. Do not
> ask the user to name a college when the intent is to discover multiple
> colleges.
>
> Add unit tests for spelling variations, short follow-ups, missing
> fields, conflicting profile updates and category ambiguity.

------------------------------------------------------------------------

## 4. Task 3 --- Persistent conversation memory and student profile

### Goals

Maintain context across turns and, where supported, across application
restarts.

Suggested profile fields (store only what is necessary): - session/user
identifier; - exam; - percentile; - merit rank; - category as stated; -
normalized seat type, if confirmed; - domicile/home-university details,
if relevant; - location preference; - preferred branches; - budget/fee
preference, if provided; - preferred ranking criteria; - last shortlist
IDs and evidence references; - last query and timestamp.

### Exact prompt

> Implement reliable session-based conversation memory in the existing
> AI-CON application.
>
> First inspect the current `_conv_context` or equivalent implementation
> and determine whether it is process-local, request-local, or
> persistent. Preserve existing interfaces where possible.
>
> Create a typed student profile and conversation state. Persist state
> in the existing database if one is already configured; otherwise
> propose the smallest compatible storage option and explain the
> trade-off before introducing a new dependency.
>
> Requirements: 1. Every conversation has a stable session ID. 2.
> Extracted student details are stored as structured fields, not only as
> a chat transcript. 3. A new explicit value updates the previous value
> and records when it changed. 4. Missing values remain unknown; never
> infer category, domicile or rank. 5. Follow-up queries inherit
> relevant prior context. 6. Store the last result set as institute
> codes and branch identifiers, not only generated prose. 7. "Rank these
> colleges by ROI" must rank the previous shortlist. 8. "Show 30
> instead" must update the requested count. 9. "Change my percentile to
> 95" must update only the percentile. 10. Support clearing/resetting a
> session and avoid mixing two users' contexts. 11. Keep secrets and
> unnecessary sensitive information out of logs.
>
> Add tests proving that context survives multiple turns and does not
> leak between sessions. Add a migration only if required and make it
> backward-compatible.

------------------------------------------------------------------------

## 5. Task 4 --- Structured college discovery (not vector-only discovery)

### Goals

Use structured data to enumerate colleges; use vectors for qualitative
descriptions.

### Exact prompt

> Fix college discovery so it searches the complete authoritative
> college master dataset rather than relying on Chroma semantic top-k
> results.
>
> Inspect the college JSON/CSV schema and cutoff institute-code mapping
> first. Build a structured discovery service that: - filters by
> state/district/city or configured location scope; - filters by
> canonical branch taxonomy; - resolves institute code and official
> institute name; - deduplicates by institute code; - retains all
> matching branches under each college; - optionally filters by
> historical cutoff availability; - returns the actual total matching
> institute count; - supports pagination and a requested result limit.
>
> For a 30-college request, return up to 30 unique institutes. Do not
> count multiple branches at one institute as separate colleges. If only
> 17 institutes match, return 17 and explain why.
>
> Do not use vector similarity as the mechanism for exhaustive
> enumeration. Use vector search after discovery to retrieve qualitative
> facts for the already identified institute codes.
>
> Add diagnostics for: - total master colleges; - total colleges with
> valid institute codes; - total Pune-scope colleges; - colleges with
> each requested branch; - colleges with cutoff records; - unmatched
> institute codes.
>
> Add tests for duplicate branches, duplicate names with different
> codes, missing codes, location aliases, Alandi/Wagholi scope and exact
> result counts.

------------------------------------------------------------------------

## 6. Task 5 --- Branch taxonomy and canonical entity resolution

### Goals

Avoid false branch matches and incomplete/truncated names.

### Exact prompt

> Create a canonical branch taxonomy for engineering admission
> discovery. Inspect all branch names in the master dataset and cutoff
> dataset before designing aliases.
>
> Group branches into explicit categories, for example: - Computer
> Engineering; - Computer Science and Engineering; - Information
> Technology; - CSE (Artificial Intelligence); - CSE (AI & Machine
> Learning); - CSE (Data Science); - Artificial Intelligence and Data
> Science; - Artificial Intelligence and Machine Learning; - Computer
> Engineering (Software Engineering); - Electronics and Computer
> Engineering.
>
> Do not assume all of these are equivalent. Store exact official branch
> names and codes, plus a separate broader family/group. Make the user's
> requested scope configurable.
>
> Matching must return exact branch, canonical group, match reason and
> confidence. Do not silently label Electronics and Computer Engineering
> as Computer Engineering.
>
> Resolve colleges by institute code first. Names are aliases for
> discovery, not unique identifiers. Detect ambiguous names and
> duplicate institute records.
>
> Preserve complete branch names in API responses, UI and PDF exports.
> Add tests for all observed aliases and near-matches.

------------------------------------------------------------------------

## 7. Task 6 --- Cutoff retrieval correctness and evidence integrity

### Goals

Ensure every cutoff is matched on all relevant dimensions.

### Exact prompt

> Audit `CutoffAgent` and every caller. Verify the exact cutoff record
> schema and implement strict retrieval using: - institute code; - exact
> branch code/name; - academic year; - seat type/quota; - category; -
> CAP round; - stage; - allocation/seat pool where applicable.
>
> Do not use `results[0]` until records have been deterministically
> filtered and sorted according to an explicit rule. Never mix rank and
> percentile. Never mix different categories, seat pools, branches,
> years, rounds or stages.
>
> For discovery, retrieve cutoff evidence for every discovered
> institute/branch pair. Return all available requested-year/round
> records or a clearly defined latest-available record. Do not claim
> that a missing record means the college/branch does not exist.
>
> Include evidence ID, source file, academic year, round, stage, seat
> pool, category, branch code, closing rank and closing percentile when
> present. Preserve missing fields as missing.
>
> Add cross-checks that parse evidence IDs and compare their encoded
> dimensions with the returned record. If they disagree, mark the record
> invalid and do not show it as verified.
>
> Add tests for wrong category, wrong branch, wrong round, multiple
> years, duplicate rows, absent records and rank/percentile separation.

------------------------------------------------------------------------

## 8. Task 7 --- Recommendation tiers and CAP option strategy

### Goals

Make safety/target/reach labels deterministic and transparent.

### Exact prompt

> Audit `RecommendationEngine` and `OptionFormPlanner`. Keep eligibility
> rules separate from historical competitiveness.
>
> Fix the current selection logic so it: 1. Uses the exact relevant
> student category/seat type. 2. Uses the same metric on both sides of a
> comparison. 3. Uses the requested or explicitly selected reference
> year and round. 4. Does not silently pick an arbitrary first record.
> 5. Explains the margin between student percentile/rank and historical
> closing cutoff. 6. Labels results as historical comparisons, not
> admission probabilities. 7. Separates `ineligible`,
> `eligibility_unresolved`, `insufficient_evidence`, `reach`,
> `competitive`, and `historically_more_attainable`.
>
> Review the existing percentile thresholds (currently +2.0 for
> historically more attainable and -2.5 for reach) with tests and
> document them as configurable heuristics, not scientifically validated
> probabilities.
>
> Do not call a college "safe" or promise a seat. Prefer wording such as
> "historically more attainable based on the selected past round."
>
> For CAP preference ordering, preserve the student's actual preference
> order within each tier and explain that CAP allotment depends on
> official rules and the submitted option form.
>
> Add tests for boundary values and missing evidence.

------------------------------------------------------------------------

## 9. Task 8 --- Popularity ranking with evidence

### Goals

Do not generate arbitrary popularity scores.

### Exact prompt

> Inspect the available college dataset and identify which fields can
> legitimately support a popularity ranking. Do not assume popularity is
> present merely because a model can generate a number.
>
> Design an explainable popularity score only from available, defensible
> signals. Candidate signals may include verified applicant
> preference/allotment data, official demand indicators or consistently
> sourced public ranking data. Do not treat NAAC grade, NIRF rank,
> placements or vector similarity as popularity by themselves.
>
> For every signal, record source, date/year, scale, normalization and
> missing-data handling. If no valid popularity data exists, do not
> fabricate a score. Return "popularity data unavailable" and offer a
> separate ranking by a clearly named measurable criterion.
>
> If a composite score is justified, expose component scores and
> weights. Make weights configurable and test that missing values do not
> silently inflate a college's score.
>
> Ensure popularity ranking is independent of admission feasibility: a
> popular college can still be a reach at the student's percentile.

------------------------------------------------------------------------

## 10. Task 9 --- ROI ranking with verified data

### Goals

Calculate ROI transparently and avoid unsupported "Tier 2 / Moderate"
labels.

### Exact prompt

> Audit the college fee and placement data schemas. Implement an
> explainable ROI comparison using only comparable, sourced values.
>
> Before calculating, normalize: - fee period and fee type (annual
> tuition, total course fee, hostel, other charges); - placement year; -
> median versus average package; - package units and currency; -
> course/branch scope; - source and verification status.
>
> Prefer branch-specific median placement package and total comparable
> tuition cost when both are available. If only institute-level
> placement data exists, label it as institute-level, not branch-level.
>
> Never calculate ROI from annual fees divided into a package without
> explaining the chosen formula and time horizon. A simple
> package-to-total-tuition ratio is only a proxy, not a true financial
> ROI. Label it clearly.
>
> If either side is missing or incomparable, mark ROI as
> `not_computable`; do not invent a moderate/high/low tier.
>
> Show source, year, formula, inputs and limitations for each college.
> Add tests for annual-vs-total fee mismatches, median-vs-average
> mismatch, missing data and outliers.

------------------------------------------------------------------------

## 11. Task 10 --- Vector index and qualitative retrieval

### Goals

Use semantic retrieval for what it is good at, not for exhaustive
filtering.

### Exact prompt

> Audit `build_vector_index.py`, the source college dataset, Chroma
> collection metadata and `CollegeInfoAgent`.
>
> Verify: - the embedding model used at index build time; - the
> embedding model used at query time; - collection name and persistence
> path; - document/chunk IDs; - institute code and record ID metadata; -
> chunk type and source URL/page; - duplicate/stale chunks; - collection
> count versus source record count.
>
> Ensure that index construction and query use the same embedding model
> and compatible preprocessing. Do not silently reuse an index built
> with a different embedding model.
>
> Add metadata filters by institute code and chunk type. Use structured
> college discovery to identify colleges first, then retrieve
> qualitative chunks for those codes.
>
> Return source metadata and retrieval distance/score. Establish a
> measured relevance threshold using a small labelled evaluation set; do
> not invent a universal threshold.
>
> Add a safe index rebuild command that writes to a new versioned
> directory, validates counts and metadata, and only switches the active
> index after successful validation. Preserve the previous index for
> rollback.

------------------------------------------------------------------------

## 12. Task 11 --- Audit and fix ML inference before retraining

### Goals

Trace the suspicious repeated `95.92%` prediction and `#1` rank.

### Exact prompt

> Trace the entire cutoff prediction path from API/query input to
> displayed chatbot response. Inspect training code, saved encoders,
> model feature order, feature construction, prediction functions,
> inverse transformations, rounding and response formatting.
>
> Specifically investigate why multiple college/branch combinations
> showed the same predicted percentile (\~95.92%) and closing rank `#1`.
>
> Verify: 1. The inference feature names and order exactly match
> training. 2. Categorical values use the same fitted encoder and
> unknown categories are handled explicitly. 3. No placeholder, default,
> zero, constant or missing feature is being passed for
> institute/branch/year/round/category. 4. The rank model's target and
> output are interpreted correctly. 5. No scaler/encoder inverse
> transform is omitted or applied twice. 6. No code overwrites
> prediction with a constant or formats a missing rank as 1. 7. The
> output is not mixing a rank percentile, closing rank and model
> prediction. 8. The model is not being asked to predict outside its
> training distribution without a warning.
>
> Add unit tests with multiple known feature combinations and assert
> that predictions are finite, correctly typed and not all accidentally
> identical. Do not assert that all different inputs must always produce
> different outputs; instead compare against known expected behaviour
> and inspect feature sensitivity.
>
> If the model output is invalid, return `prediction_unavailable` and
> explain why. Never substitute rank 1 or a generic cutoff.
>
> Keep a diagnostic mode that logs feature names and safe feature
> values, model artifact version and prediction output, but no personal
> secrets.

------------------------------------------------------------------------

## 13. Task 12 --- ML dataset audit and retraining design

### Current reported metrics

A training report shared with the project showed: - Samples: 116,744 -
Train: 99,232 - Test: 17,512 - Rank MAE: 28,348.76 - Rank RMSE:
35,719.52 - Rank R²: 0.5713 - Percentile MAE: 15.04 points - Percentile
RMSE: 19.22 points - Percentile R²: 0.5261

These metrics are a warning, but they do not by themselves prove that
retraining is the only fix. First verify the data and inference
pipeline.

### Exact prompt

> Audit the cutoff training dataset before training any new model.
>
> 1.  Inspect the complete training script and raw/processed data
>     schema.
> 2.  Identify target leakage, duplicate records, conflicting records,
>     impossible percentiles/ranks, missing fields, category imbalance
>     and year imbalance.
> 3.  Verify the meaning and scale of `closing_rank` and
>     `closing_percentile`. Check whether the percentile values are
>     valid and whether a value such as 1.3199 is a legitimate source
>     record or a data-conversion problem.
> 4.  Group records by institute, branch, category, seat pool, year,
>     round and stage. Detect duplicate or contradictory rows.
> 5.  Verify that feature columns do not contain direct or indirect
>     copies of the target.
> 6.  Save a data-quality report before dropping or correcting any
>     record. Never silently discard data.
> 7.  Compare a simple baseline (for example, historical
>     latest-year/median cutoff) with ML performance.
> 8.  Use chronological validation: train on older years and validate on
>     a later unseen year. If enough data exists, use rolling-origin
>     validation. Do not rely only on random row splitting.
> 9.  Consider group-aware validation to test generalization to unseen
>     institutes/branches separately.
> 10. Fit encoders and all preprocessing only on the training partition.
>     Persist the exact preprocessing pipeline with the model.
> 11. Report MAE, RMSE, R², median absolute error and error by
>     year/category/branch/college. Report sample counts for every
>     slice.
> 12. Compare candidate models and retain the simplest model that beats
>     the baseline on the chronological holdout.
>
> Do not retrain the production model until the audit report and
> validation split are reviewed. Save new artifacts under a versioned
> directory and keep the current artifacts unchanged.

------------------------------------------------------------------------

## 14. Task 13 --- Better model design and target strategy

### Exact prompt

> Based on the audited data, propose a model design for historical CAP
> closing cutoffs. Do not assume one regressor is suitable for both rank
> and percentile.
>
> Evaluate: - predicting percentile and rank as separate targets; -
> predicting one target and deriving the other only if a validated
> official conversion is available; - log-transforming highly skewed
> rank targets, with correct inverse transformation and evaluation in
> original rank units; - categorical encoding appropriate for institute,
> branch, category, seat pool, round and year; - models such as
> HistGradientBoosting, Random Forest, ExtraTrees, CatBoost or LightGBM
> only if dependencies and data support them; - a historical baseline
> and uncertainty intervals or prediction ranges.
>
> Avoid arbitrary ordinal encodings for nominal categories unless the
> model and encoding are justified. Use a fitted preprocessing pipeline
> and explicit unknown-category behaviour.
>
> Evaluate future-year generalization and performance on common versus
> rare colleges/branches. Record the training data version, code
> version, feature schema, model parameters and metrics.
>
> The prediction output must be a range or point estimate with a clear
> uncertainty/validation warning, not a false admission probability. If
> validation is poor for a segment, abstain for that segment.

------------------------------------------------------------------------

## 15. Task 14 --- Qwen generation and evidence-grounding

### Goals

Qwen should explain evidence, not invent or calculate it.

### Exact prompt

> Audit the Qwen prompt construction and response parsing. Keep
> deterministic retrieval, calculations and ranking outside the LLM.
>
> Supply Qwen with a compact structured payload containing: - normalized
> student profile; - explicit query intent; - exact discovered
> institute/branch candidates; - historical cutoff records and evidence
> IDs; - sourced college facts; - model predictions and validation
> metadata; - ranking components and formulas; - missing-data flags.
>
> Instruct Qwen to: 1. Use only supplied evidence. 2. Preserve exact
> institute names, codes, branch names, years, rounds and categories. 3.
> Never fabricate a college, cutoff, rank, fee, package, popularity
> score, ROI or citation. 4. Clearly distinguish historical observations
> from ML predictions. 5. State when data is missing or conflicting. 6.
> Never claim admission is guaranteed. 7. Avoid truncating branch names
> or omitting records because of response length. 8. Return structured
> JSON matching a validated response schema before rendering prose.
>
> Validate the JSON. If validation fails, retry once with a repair
> prompt or return the deterministic evidence table. Do not silently
> display malformed output.
>
> Test with adversarial prompts that ask the model to invent missing
> cutoffs or guarantee admission.

------------------------------------------------------------------------

## 16. Task 15 --- Web scraper fallback and source verification

### Exact prompt

> Audit the existing scraper/cache before changing it. Implement scraper
> fallback only for fields missing from the local authoritative dataset.
>
> For every scraped field, store: - value; - source URL; - page title or
> publisher; - retrieval timestamp; - applicable academic/placement
> year; - extraction method; - confidence/verification status; - field
> scope (college-level or branch-level).
>
> Prefer official CET Cell, institute, AICTE, NBA, NAAC and other
> primary sources where applicable. Secondary sources may be used only
> with explicit source labels.
>
> Do not scrape a value and mark it verified merely because a page
> returned text. Detect stale pages, conflicting values and year
> mismatches. Cache with a defined expiry and respect website terms and
> rate limits.
>
> Never let scraped facts overwrite official historical cutoff records
> without an explicit reconciliation workflow. Keep citations attached
> to each fact through retrieval and final response.

------------------------------------------------------------------------

## 17. Task 16 --- API, UI and PDF output

### Exact prompt

> Inspect the existing API/UI and PDF report generation. Update the
> response contract so the UI does not have to infer missing data from
> prose.
>
> A discovery response should include: - request/session ID; - parsed
> student profile; - geographic scope; - requested unique college
> count; - actual matching unique college count; - ranking method; -
> ordered colleges; - all matching branches per college; - historical
> cutoff evidence per branch; - model prediction and validation status,
> if available; - sourced fees/placements/accreditation facts; -
> popularity/ROI components or an explicit unavailable status; -
> citations and warnings.
>
> Display the exact count of unique colleges separately from
> branch-option count. Add filters and pagination if the result set is
> large.
>
> PDF export must use the same validated structured response as the UI.
> Do not generate a PDF containing facts that are absent from the
> on-screen evidence. Include report date, source dates, historical-data
> disclaimer and missing-data notes.
>
> Ensure long branch names and college names wrap rather than truncate.

------------------------------------------------------------------------

## 18. Task 17 --- Performance and reliability

### Exact prompt

> Profile AI-CON before optimizing. Measure startup time, structured
> discovery time, cutoff retrieval time, vector retrieval time, scraper
> latency, model inference time and response generation time.
>
> Optimize only measured bottlenecks. Add indexes to frequently filtered
> structured fields if the current database supports them. Cache stable
> institute/branch lookups and avoid rebuilding the vector index at
> every request.
>
> Add bounded timeouts and graceful degradation: - if Qwen is
> unavailable, return structured evidence; - if vector retrieval is
> unavailable, continue with structured cutoff discovery; - if scraper
> is unavailable, show local evidence and missing fields; - if ML
> prediction is invalid, omit the prediction and explain why.
>
> Avoid broad `except Exception` blocks that silently turn real bugs
> into empty results. Log the exception with a correlation ID and return
> a controlled error status.
>
> Add tests for each degraded mode.

------------------------------------------------------------------------

## 19. Task 18 --- End-to-end acceptance tests

### Exact prompt

> Run the following end-to-end test cases against a test copy of the
> current AI-CON data:
>
> **Test A --- Discovery** "I have 94 percentile in MHT-CET, OPEN
> category, and want the 30 most popular Pune colleges for Computer
> Engineering and related branches."
>
> Expected: - Parsed profile is visible and correct. - Category/seat
> code ambiguity is handled according to admission rules. - Search
> covers the full structured master dataset. - Up to 30 unique
> institutes are returned, not 30 branch rows. - Every institute has a
> valid code and official name. - All matching branches are grouped
> under each institute. - No unsupported popularity score is fabricated.
>
> **Test B --- Admission feasibility** "Classify these colleges as
> historically more attainable, competitive and reach."
>
> Expected: - Exact category, branch, year, round and seat pool are
> used. - Each classification includes the cutoff, student margin and
> evidence ID. - No admission guarantee or invented probability appears.
>
> **Test C --- Follow-up memory** "Now rank these by ROI."
>
> Expected: - Reuses the previous shortlist and student session. - Does
> not ask which college. - Computes ROI only where comparable verified
> data exists.
>
> **Test D --- Update profile** "Change my percentile to 95 and show the
> list again."
>
> Expected: - Only percentile changes. - Previous location, category and
> branches remain intact. - New feasibility classifications are
> recalculated.
>
> **Test E --- ML prediction** Predict for multiple known
> institute/branch/category/round combinations.
>
> Expected: - Correct feature schema and transformations. - No hardcoded
> identical output or rank 1 fallback. - Predictions are finite and
> within validated target bounds. - Prediction limitations are visible.
>
> **Test F --- Missing evidence** Ask for a college/branch/category
> combination with no matching record.
>
> Expected: - Explicit `insufficient_evidence`. - Exact missing
> dimension(s) identified. - No nearest unrelated cutoff substituted.
>
> **Test G --- Exact college facts** Ask about affiliation, fees,
> placements and accreditation.
>
> Expected: - Each fact has its own source, date and scope. - No
> institute-level placement figure is presented as branch-level.
>
> Record test results and sample outputs. Fix failures before release.

------------------------------------------------------------------------

## 20. Task 19 --- Final audit and release checklist

### Exact prompt

> Perform a final code, data and model audit after all tasks are
> implemented.
>
> Produce: 1. Architecture diagram and updated component
> responsibilities. 2. List of changed files and why each changed. 3.
> Database/schema migrations. 4. Dataset-quality report. 5. Vector-index
> validation report. 6. ML baseline-versus-new-model comparison using
> chronological holdout metrics. 7. Prediction inference tests. 8.
> End-to-end test results. 9. Known limitations and unsupported fields.
> 10. Exact startup, test and retraining commands. 11. Rollback
> instructions for code, vector index and model artifacts.
>
> Do not mark a feature complete if its acceptance test is failing. Do
> not claim "verified", "accurate", "popular", "high ROI" or "high
> probability" unless the system has a documented definition and
> supporting evidence.
>
> Keep the old model and index available until the new versions pass
> acceptance tests. Summarize what is safe to deploy and what still
> needs manual review.

------------------------------------------------------------------------

## 21. Suggested implementation order

  ----------------------------------------------------------------------------
                         Order Task                      Must happen before
  ---------------------------- ------------------------- ---------------------
                             1 Baseline and tests        All code changes

                             2 Query understanding and   Discovery and memory
                               routing                   integration

                             3 Conversation memory       Reliable follow-ups

                             4 Structured college        30-college output
                               discovery                 

                             5 Branch taxonomy and       Accurate branch
                               entity resolution         matching

                             6 Cutoff retrieval and      Feasibility ranking
                               evidence integrity        

                             7 Recommendation and option Admission
                               planner                   classification

                             8 Popularity ranking        Popularity claims

                             9 ROI ranking               ROI claims

                            10 Vector index audit        Qualitative retrieval

                            11 ML inference audit        Any retraining

                            12 Dataset audit and         Retraining
                               validation design         

                            13 Model                     Prediction release
                               comparison/retraining     

                            14 Qwen grounding            Final answer
                                                         generation

                            15 Scraper verification      Missing facts

                            16 UI/PDF contract           User-facing release

                            17 Performance/reliability   Production hardening

                            18 End-to-end acceptance     Release
                               tests                     

                            19 Final audit               Deployment
  ----------------------------------------------------------------------------

------------------------------------------------------------------------

## 22. Non-negotiable engineering rules

1.  Never fabricate missing data.
2.  Never treat vector top-k as an exhaustive college directory.
3.  Never count multiple branches at one institute as multiple colleges.
4.  Never mix rank and percentile.
5.  Never mix different quota/category/seat-pool records.
6.  Never silently select the first cutoff record.
7.  Never present an ML estimate as an official cutoff.
8.  Never show rank `1` as a fallback.
9.  Never invent popularity or ROI scores.
10. Never discard old artifacts before a replacement is validated.
11. Never use Qwen for deterministic filtering or numerical
    calculations.
12. Never let a follow-up query lose the active student profile.
13. Never describe historical attainability as an admission guarantee.
14. Every displayed cutoff/fact must retain its evidence/source
    reference.
15. Every task must have tests and a documented result.

## 23. First instruction to start the work

Give the coding agent this instruction first:

> Read this entire `AI_CON_IMPROVEMENT_PLAN.md` before modifying the
> repository. Start with Task 0 and Task 1 only. Inspect the actual
> codebase, map the architecture, reproduce the known defects and create
> baseline regression tests. Do not retrain the model or modify the
> production vector index yet. Report the files inspected, defects
> reproduced, tests added, test results and the exact next task. Wait
> for my approval before moving to the next major phase.
