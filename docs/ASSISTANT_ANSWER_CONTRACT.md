# Application-owned analytical answer contract

The assistant resolves a structured request before executing any tool: metrics,
entity identities, scope, aggregation/detail grain, transaction dates, stock cutoff
or forecast horizon, ranking axes versus displayed measures, direction, result
count, temporal extrema, references, explicit overrides and answer components.
All numeric answers originate in approved read-only analytics services.

## Ranking policy

Unqualified **best-selling / أكتر منتجات مبيعاً** means **recorded sold units**,
not sales value, stock balances, profit or forecast demand. The answer explicitly
labels units. An explicit ranking axis (`by sales value`, `حسب المبيعات`, etc.)
takes precedence; additional displayed measures do not create a second ranking.
The transaction dates and original before-refund accounting basis still apply.
Different explicitly requested rankings retain separate axes and populations.

Arabic/English rank count syntax supports count-before-entity word order,
Arabic/Western numerals and common number words. Counts must remain within the
public 1–20 row contract. Distinct, ordered, verified identities and measures
must cover the requested top-K (or all eligible entities if fewer exist).
Safety caps and missing cells remain partial, not complete top-K evidence.

## Time series and multi-metric comparisons

Monthly/yearly series are validated against the requested calendar periods.
Missing/duplicate/conflicting periods, unavailable measure cells and flagged
partial periods prevent complete status. Missing months are unknown, not zero.
Explicit highest and lowest requests are separate obligations; all tied period
identities are retained. Extrema on incomplete evidence are labeled as applying
only to available periods, not the full requested window. Daily/weekly period
gap validation retains existing service policies; no new calendar filling or
imputation is introduced.

A branch-pair comparison must cover every requested supported metric for both
entities. An explicit new pair without a reference or a new detailed grain
clears incompatible inherited product/time detail, preserving compatible filters
and explicit dates. Financial/category-pair and inventory limitations remain.

## Connected mode and bounded recovery

Groq remains the exclusive API provider. A benign completion with no tool calls
can execute an already resolved application-owned approved plan. This introduces
no extra HTTP requests. It requires known metrics, no unresolved constraints,
compatible tools and the same registry, scope, output and privacy validation.
It respects remaining tool count, cancellation and turn time, memoizes results,
checks database source stability and never retries failed tools speculatively.

Malformed/unadvertised tool selections, protocol failures, provider errors,
authentication/model-access failures and exhausted API budgets do not trigger
this recovery. Supported evidence is retained when execution is partial.
Diagnostics distinguish provider-selected evidence from server-plan recovery;
they contain approved operations, validated arguments and sanitized reasons,
never credentials, raw provider prose or private customer records.

Full status requires metric, scope, answer-component and answer-shape coverage.
Presentation lists essential ranked entities and requested periods, all requested
comparison metrics and extrema; it does not substitute an arbitrary first row.
Critical limitations remain visible; detailed evidence/methodology remain in
the existing bilingual, RTL-aware expanders. No model-authored HTML or numbers
are rendered. Local/mock tests do not establish live Groq understanding.
