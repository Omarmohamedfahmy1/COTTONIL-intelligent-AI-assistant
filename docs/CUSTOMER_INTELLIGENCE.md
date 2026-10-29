# Phase 8 customer intelligence and evaluated research

Phase 8 expands the existing Customer Intelligence page and bounded local
assistant. It retains the eight functional modules, the read-only financial
foundation, Phase 6 inventory formulas and Phase 7 forecasting implementation.
`predictive.py` and its private legacy customer artifacts remain unchanged.
Research below is historical, not live company data or production approval.

## Source audit and identity coverage

The original SQLite dataset records 540,000 orders from 2018-10-19 through
2026-10-18. Of these, 437,039 have an identified customer and 102,961 are anonymous:
80.9331% order-identification coverage. There are 85,000 unique registered master
customers and 74,660 distinct identified purchasers across the full observed
history; 10,340 registered customers have no identified purchase. There are no
duplicate master IDs, missing customer-master matches or purchases before the
**normalized** registration date. Raw registration strings are M/D/YYYY and must
not be compared lexicographically. Normalized registration coverage matches the
order coverage. Registered master segments are Retail (83,334) and B2B reseller
(1,666), descriptive source attributes, not inferred behavior segments.

Identified recorded revenue before tax/refunds totals EGP 680,321,158.81;
anonymous recorded revenue EGP 160,953,017.51; total EGP 841,274,176.32. There are
64,799 full-history repeat identified purchasers and **64,688 customers with
purchases at multiple locations**. A branch filter never creates customer
ownership. Anonymous purchases are not allocated to the master or a model.

Identity coverage is observational and potentially biased: an identified sample
need not represent anonymous buyers. Source provenance is unverified. First
recorded purchase is left-censored by source coverage and need not be true
acquisition. Customer registration, first purchase and model eligibility are
separate definitions. No names or contact fields are loaded by the new services.

## Architecture and scope

- `customer_data.py`: internal history, fixed RFM scoring and disclosure guard.
- `customers.py`: public aggregate behavioral dashboard, audit and cohorts.
- `customer_models.py`: temporal churn/value research, metrics and gates.
- `customer_tools.py`: seven fixed read-only aggregate assistant tools.
- `ui/pages/customers.py`: overview, RFM, retention, repeat purchase, revenue
  research, churn evaluation and limitations views, with bilingual labels.

History reuses the approved `metrics._orders` source, one row per matching order.
Category revenue is the selected lines aggregated **before** header joining.
Order/customer counts are not additive across categories, branches or months.
Global date/location/type/category filters apply to recorded purchasing behavior.
The registered count is company-wide through the capped observed end date.
RFM uses a fixed 365-day lookback ending observed end, independent of display
start; recency covers all historically observed identified scoped purchasers.
Research models are explicitly company-wide at the latest source cutoff;
display filters do not silently retrain a different study. Tools disclose that
scope override and the actual model study dates.

## Customer definitions and formulas

| Metric | Definition |
|---|---|
| Registered customers | Company normalized master registration <= observed end |
| Identified purchasing / active customers | Distinct non-null purchasing IDs in selected period/scope |
| Anonymous orders | Selected orders with null customer ID; no assumed identity |
| New purchasers | Selected purchasers whose first company-wide recorded order is in selected period |
| Returning purchasers | Selected purchasers whose first company-wide recorded order predates period start |
| Repeat purchasers | Selected identified purchasers with >=2 distinct selected orders in period |
| Repeat purchase rate | 100 × repeat purchasers / identified purchasers; unavailable for no purchasers |
| Purchasing frequency | Identified selected orders / distinct identified purchasers |
| Average recorded spend | Selected identified revenue / distinct identified purchasers |
| Identified revenue contribution | Identified revenue / all selected revenue; unavailable when total <=0 |
| Recency | Observed end minus last recorded selected-scope purchase, in days |

New and returning are mutually exclusive and reconcile to the distinct period
purchaser count. Repeat purchasing within a period is a separate concept: a new
purchaser can buy twice. Monthly counts/rates do not sum into period counts/rates.
All revenue is recorded revenue excluding tax and before refunds, not customer
profit or net profit. No unsupported return-adjusted customer spending is invented.

## Descriptive RFM

At exclusive cutoff C (day after observed end), include identified purchasers
active in `[C−365 days,C)`. Recency is measured to C−1; frequency counts distinct
orders and monetary sums the matching recorded scoped revenue in that window.

| Score | R: days since last purchase | F: orders | M: EGP recorded revenue |
|---:|---|---|---|
| 5 | <=30 | >=5 | >6000 |
| 4 | 31–90 | 4 | >3000 through 6000 |
| 3 | 91–180 | 3 | >1500 through 3000 |
| 2 | 181–270 | 2 | >500 through 1500 |
| 1 | >270 | 1 | <=500 |

Fixed engineering thresholds, not future-fitted quantiles. Assign exactly one
segment in this priority: inactive (R<=2 / >180 days), high historical spend
(M>=4), frequent (F>=4), recent (R>=4), otherwise infrequent. These labels do not
prove churn. A >365-day inactive purchaser remains in all-history recency but is
outside the current RFM eligibility window.

Movement tracks the cohort eligible 90 days earlier, retaining its earlier
segment, and joins the current descriptive segment or 'outside current window'.
Frequency changes compare that same earlier population's two overlapping
365-day order counts, filling current no-observed-purchase frequency with zero.
This is descriptive behavior in the selected scope, not causal attrition or
exclusive location membership. Small transition families can be unavailable.

## Acquisition cohorts and repeat observation

Cohort month is first recorded purchase **within the selected purchasing scope**,
using all available scoped history through the selected observed end. It is not
registration. For a company scope this is first recorded company purchase; for a
location/category it is first recorded purchase there. Do not add scoped cohorts
to create company counts or interpret them as branch ownership.

Only fully observed acquisition calendar months within the requested range are
shown. Retention age 0–12 is distinct cohort purchasers with a recorded scoped
purchase in that full follow-up month / cohort size. Future and partial months
are unavailable (blank), never zero or 'churned'. October 2026 is partial and is
not a complete retention month. Age zero is 100% for eligible full cohorts.
Time to second purchase uses the second distinct order (same-day orders can yield
zero days). Its median is conditional on observed repeaters, not a survival
estimate. Recent cohorts have less follow-up; do not compare their cumulative
repeat rates as if exposure were equal. Follow-up days are reported explicitly.

## Temporal label construction and leakage controls

The exclusive latest prediction cutoff is **2026-10-19**, after the last observed
day. Five annual research cohorts use cutoffs 2021-10-19, 2022-10-19, 2023-10-19,
2024-10-19 and 2025-10-19. Features always precede C, from `[C−365,C)`.

- Eligible: an identified purchaser with a recorded order in that prior window.
- Churn research label: no identified recorded purchase in `[C,C+180 days)`.
- Value target: sum of recorded identified revenue in `[C,C+365 days)`.
- Reject a cohort whose exclusive outcome end exceeds source-last-day + 1.
  Missing future periods are never assigned zero labels.

The 180-day definition measures observed inactivity. Retail replacement cycles,
unidentified purchases, other retailers and missing cross-channel identity can
make it unsuitable as literal customer loss. Eligibility excludes registered
never-purchasers, anonymous orders and purchasers outside the lookback.

Train on the first two cohorts (49,669 rows / 33,755 unique customers); validate
on 2023-10-19 (33,605 rows). Training 365-day outcomes finish before validation
prediction. Validation 365-day outcomes finish before the first test cutoff.
Lock model/selection before the two held-out tests, 2024-10-19 and 2025-10-19:
85,258 rows representing 59,455 unique customers. Outcome ends are computed by
actual 180/365-day durations, not assumed calendar anniversaries in leap years.
Exact feature/outcome dates are in the validation JSON schedule.

No random row split. Scaling and RFM segment value means are fitted only on
training cohorts. Feature construction ignores all records at/after C; only label
construction reads future outcomes. No future stock, promotion or registration
features enter the models. Test future-value mutation tests confirm validation
selection remains unchanged. Models are not switched after test scoring.

Repeated people across temporal cohorts are expected, not silently independent:
23,311 customers overlap training/validation; 68.4112% of held-out rows concern
people seen in training or validation. Seen/unseen diagnostics are reported.
Customer-cluster bootstrap (80 seeded resamples) preserves repeated-customer
membership in the pooled tests. Its 2.5/97.5 percentile ROC ranges are conditional
descriptive ranges, not guarantees for new populations or future dates. There
are only two held-out annual cohorts; no independent-market validation exists.

## Churn candidates, evaluation and suppression

Candidates: constant training prevalence; recency-only scaled logistic regression;
fixed RFM score `1−(R+F+M)/15`, clipped to [.01,.99]; scaled multi-feature logistic
regression (C=1, max_iter=500); histogram gradient classifier with the legacy
experimental family/settings (100 iterations, 15 leaves, L2 4, rate .07, seed 42).
Features: recency, frequency, monetary, distinct locations, orders in prior 90/180
days, observed activity span, mean gap, and recent-minus-previous-90-day counts.
The RFM score is a heuristic baseline, not an asserted calibrated probability.

Report ROC-AUC, stepwise PR Average Precision (not trapezoidal PR area), prevalence,
precision/recall, TN/FP/FN/TP at a fixed diagnostic threshold .5, Brier score,
10 equal-width-bin calibration error and observed-versus-estimated bin means.
Threshold .5 is not a validated intervention-cost policy. Single-class ROC/AP are
unavailable rather than fabricated; finite probability validation is enforced.

A nonconstant model can be selected only if validation ROC>=.60, AP>=prevalence+.03,
Brier<=95% of constant-baseline Brier, calibration error<=.05 and N>=100. Select
lowest validation Brier among qualifiers; otherwise retain prevalence. Held-out
pooled and per-cohort gates must also pass for evaluated-research status. These
are explicit engineering screens, not scientific proof of business reliability.

**Actual decision: Experimental / unreliable.** No candidate qualifies on
validation. The constant baseline is retained. Held-out histogram ROC is near
.50, with AP near prevalence; the report gives exact numbers. No actionable
individual probabilities, customer risk bands or automatic marketing actions are
published, regardless of the research state. Descriptive RFM/cohorts stay available.

## Finite-horizon customer revenue proxy

The target is **predicted next-365-day recorded customer revenue**, never literal
infinite-horizon CLV, net profit, or customer lifetime profit. It covers eligible
identified recent purchasers only; it excludes anonymous revenue and is not a
reconciliation forecast for all company sales in Phase 7.

Candidates: training future-revenue mean; training future-revenue median; repeat
past-365-day spend; training RFM-segment future-revenue mean (fallback train mean);
scaled Ridge alpha 100; log1p-target histogram regression (same experimental family,
seed 42). Report MAE, WAPE, RMSE, sMAPE, signed bias and segment-level metrics.
Best validation MAE baseline is retained unless a regression improves it by >=5%.
Tests cannot choose a replacement model. Value research is unreliable when held-out
MAE exceeds 110% of baseline, WAPE>60%, or absolute percentage bias>20%.

**Actual decision: Experimental / unreliable.** The training median baseline wins
validation; low per-customer MAE does not make the sum a calibrated expected total.
It severely underpredicts aggregate revenue. The aggregate experimental point
estimate is labeled accordingly and must not be used for planning. No calibrated
value interval is available. A final aggregate fit uses all five mature labeled
cohorts, then scores the 51,522 eligible purchasers at 2026-10-19 in memory. It
predicts through 2027-10-18; no current/future outcome is assumed observed. Only
the aggregate sum/count/dates/model/state leave the module; no prediction records
or fitted models are written. Saved legacy artifacts remain unchanged.

## Privacy, assistant and caching

Minimum group size is five. A nonzero group of 1–4 suppresses the whole additive
table family rather than leaving a reconstructible residual row. Binary repeat/
new complements are suppressed together; small active scopes suppress scoped
summary metrics. Retention suppresses a cohort row when observed active/inactive
complements are small. Monthly families with small cells are suppressed wholesale.
No names, IDs, contact details, individual probabilities or raw customer features
enter public service dictionaries, UI frames, aggregate exports or assistant data.
This is suppression, not differential privacy: arbitrary overlapping queries can
still permit differencing, and no production access-control/privacy guarantee is
claimed. Existing approved modules are preserved; this phase does not retrofit a
global disclosure budget or authentication system.

The seven tools summarize scoped purchasing, RFM revenue ranks, cohort retention,
repeat trends, same-cohort changes and company-wide churn/value research. Fixed
Arabic/English patterns clarify private requests, retain applicable global scope,
and disclose unreliable research. 'This month' anchors to the selected end capped
by source coverage, not the computer date. No Phase 9 unrestricted planning,
arbitrary SQL or live LLM provider extension is included.

Parameterized source queries use existing read-only access. Eight internal
history cache entries and sixteen aggregate scope entries key on DB path/mtime/
size and version; research has two entries. Public results are copied to protect
cached evidence. Streamlit adapters cache reruns. Fits are seeded and limited to
one numerical-library thread using existing scikit-learn dependency threadpoolctl;
no new package install was needed. Replacing database contents while preserving
mtime/size requires clearing caches/restarting; do not mutate the source in place.

## Reproduction and review

```powershell
.\.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -X utf8 scripts/validate_phase8.py --report reports/phase_8_validation_final.json
.\.venv\Scripts\python.exe -X utf8 scripts/smoke_app.py --report reports/phase_8_smoke_final.json
.\.venv\Scripts\python.exe -X utf8 scripts/verify_phase8.py
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1
```

The integration tests need the original local database; otherwise they skip
explicitly. Do not run legacy `predictive.py` to regenerate saved customer files.
See `reports/PHASE_8_REPORT.md` for exact metrics, executed commands/exit codes,
failed exploratory attempts, final tests, timings, screenshots and limits.
**STOP at Phase 8; independent review is required before Phase 9.**
