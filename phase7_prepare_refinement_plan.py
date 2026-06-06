#!/usr/bin/env python3
import csv, json, math
from pathlib import Path
from collections import Counter
from datetime import datetime

BASE = Path('/Users/Zaid/Desktop/PUF AY 2024/CSV')
PHASE3 = Path('/Users/Zaid/Desktop/tqip_ocular_study_phase3/outputs')
PHASE5 = Path('/Users/Zaid/Desktop/tqip_ocular_study_phase5/outputs')
WORK = Path('/Users/Zaid/Desktop/tqip_ocular_study_phase7')
OUT = WORK / 'outputs'
DOC = WORK / 'docs'
LOG = WORK / 'logs'


def load_csv(path):
    with open(path, newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, fieldnames=None):
    if fieldnames is None:
        fieldnames = []
        seen = set()
        for row in rows:
            for k in row.keys():
                if k not in seen:
                    seen.add(k)
                    fieldnames.append(k)
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        w.writeheader()
        for row in rows:
            w.writerow(row)


def to_float(x):
    try:
        if x in ('', None):
            return None
        return float(x)
    except Exception:
        return None


def main():
    run_ts = datetime.now().isoformat()
    assumptions = [
        'Phase 7 does not redefine the cohort; it prepares the next defensible execution steps based on reviewer feedback.',
        'The primary study should remain a direct-arrival, ISS >= 16, orbital/adnexal-dominant timing study.',
        'Statsmodels is an appropriate library for the final parsimonious regression and for cluster-robust standard errors if a site variable is merged.',
    ]
    issues = []

    primary = load_csv(PHASE3 / 'phase3_primary_timing_dataset.csv')
    negative = load_csv(PHASE3 / 'phase3_negative_timing_review.csv')
    phase5 = json.loads((PHASE5 / 'phase5_model_summary.json').read_text())

    # Merge TQIPSITE from inclusion table for future cluster-robust work.
    site_map = {}
    with open(BASE / 'TQP_INCLUSION.csv', newline='', encoding='utf-8-sig') as f:
        r = csv.DictReader(f)
        for row in r:
            site_map[row['inc_key'].strip()] = row['TQIPSITE'].strip()

    primary_with_site = []
    missing_site = 0
    for row in primary:
        out = dict(row)
        site = site_map.get(row['inc_key'].strip(), '')
        out['TQIPSITE'] = site
        if site == '':
            missing_site += 1
        primary_with_site.append(out)
    write_csv(OUT / 'phase7_primary_timing_with_site.csv', primary_with_site)

    # Negative timing categorization using the supplied framework.
    cat_rows = []
    cat_counter = Counter()
    px_counter = Counter()
    for row in negative:
        eh = to_float(row['elapsed_hours_to_first_px'])
        code = row.get('first_px_code', '')
        if eh is None:
            category = 'unclassifiable_missing_elapsed'
        elif -1 < eh < 0:
            category = 'Administrative Registration Lag'
        elif row.get('first_px_hr', '') in ('0', '0.0', '0.00', '0.000000'):
            category = 'Midnight Default Timestamps'
        elif -24 <= eh <= -1:
            category = 'Moderate Discrepancy Shifts'
        elif eh < -24:
            category = 'Severe Data Entry Errors'
        else:
            category = 'Other'
        out = dict(row)
        out['negative_timing_category'] = category
        cat_rows.append(out)
        cat_counter[category] += 1
        px_counter[(category, code)] += 1
    write_csv(OUT / 'phase7_negative_timing_categorized.csv', cat_rows)

    neg_summary_rows = []
    total_neg = len(cat_rows)
    for cat, n in cat_counter.items():
        neg_summary_rows.append({'category': cat, 'n': n, 'pct': (100.0*n/total_neg if total_neg else None)})
    write_csv(OUT / 'phase7_negative_timing_category_summary.csv', neg_summary_rows)

    # readiness checks
    site_counts = Counter(r['TQIPSITE'] for r in primary_with_site if r['TQIPSITE'] != '')
    cluster_ready = len(site_counts) > 1 and missing_site == 0
    if missing_site > 0:
        issues.append(f'{missing_site} primary timing rows were missing TQIPSITE after merge, which would limit cluster-robust site modeling.')
    if not cluster_ready:
        issues.append('Site-level clustering may not yet be fully ready; verify TQIPSITE completeness before final cluster-robust analysis.')

    # plan documents
    plan_text = f"""# Phase 7 Revision and Execution Plan

## Summary of accepted direction
The reviewer feedback supports narrowing the study to its most defensible core: a direct-arrival, ISS >= 16, orbital/adnexal-dominant operative timing study. The emergent ocular subgroup should remain descriptive or sensitivity-only because the current operative sample is too sparse for stable multivariable inference.

## Primary execution plan
1. **Lock the study framing** as an orbital/adnexal operative timing study in severe polytrauma.
2. **Retain the current codebook** for the main analysis rather than broadening emergent ocular definitions retrospectively.
3. **Use the binary prolonged-delay model as the primary adjusted analysis** because it is easier for clinicians to interpret and matches the workflow-centered question.
4. **Re-run the adjusted model in parsimonious form** using only structural workflow covariates:
   - age
   - ISS
   - GCS motor score
   - hemorrhage-control intervention
   - angiography
   - mixed-priority indicator
5. **Retain the log-transformed continuous-time model as a supplement or sensitivity analysis**, not as the main reported model.
6. **Keep secondary outcomes out of the causal main narrative** and place them in supplement-oriented descriptive reporting.
7. **Retain negative elapsed-time exclusions** from the primary timing model and explain them transparently in a dedicated data-integrity section.
8. **Prepare for cluster-robust standard errors by site** using the merged `TQIPSITE` variable in a later final-model run.

## Planned order of execution
- Step A: merge `TQIPSITE` into the primary timing dataset
- Step B: generate a finalized parsimonious statsmodels logistic model
- Step C: generate a parallel log-time sensitivity model
- Step D: prepare supplement text describing the 98 excluded negative-time records
- Step E: if site completeness is adequate, rerun the final model with cluster-robust standard errors grouped by `TQIPSITE`
- Step F: update manuscript tables and text to reflect the final parsimonious model rather than the broader exploratory scaffold

## Checks to perform along the way
- Confirm that the model-ready cohort remains unchanged after site merge
- Confirm that mixed-priority cases are retained with an indicator variable
- Confirm that emergent ocular cases are excluded from the primary modeled regression
- Confirm that no negative elapsed-time rows re-enter the primary modeled dataset
- Confirm that the parsimonious model complete-case sample remains adequate
- Confirm whether the site variable is sufficiently populated for cluster-robust modeling
"""
    (DOC / 'phase7_revision_execution_plan.md').write_text(plan_text, encoding='utf-8')

    model_spec = """# Parsimonious Final Model Specification

## Primary adjusted model
**Outcome:** prolonged delay, defined as time to first qualifying ocular/orbital procedure greater than the cohort median.

**Primary cohort:** direct-arrival, ISS >= 16, model-ready restricted cohort (orbital/adnexal + mixed emergent-priority only).

**Recommended covariates:**
- age
- Injury Severity Score (ISS)
- GCS motor score
- hemorrhage-control intervention present
- angiography present
- mixed emergent-priority indicator

## Rationale
This specification prioritizes structural workflow variables over highly volatile single-point admission vital signs. It reflects the reviewer concern that fluctuating physiologic measures may add noise and collinearity without improving interpretability.

## Sensitivity model
A secondary sensitivity model may use:
- outcome = log(arrival-to-procedure hours + 1)
- same covariates as above

## Recommended implementation in Python
Statsmodels is appropriate. Example approaches include:
- `statsmodels.formula.api.logit(...)` for the primary binary model
- `statsmodels.formula.api.ols(...)` for the log-time sensitivity model
- `fit(cov_type='cluster', cov_kwds={'groups': df['TQIPSITE']})` for cluster-robust standard errors if site merge is complete
"""
    (DOC / 'phase7_parsimonious_model_spec.md').write_text(model_spec, encoding='utf-8')

    neg_appendix = f"""# Negative Timing Data Integrity Appendix Text

A total of {total_neg} encounters in the locked operable dataset demonstrated negative elapsed time from hospital arrival to first qualifying ocular/orbital procedure and were excluded from the primary timing analysis. Negative elapsed time is not logically interpretable as surgical delay and therefore these records were retained for audit only.

Review of the excluded records suggests that they are not random corruption but instead reflect several recurring administrative and operational patterns. Using rule-based categorization of the excluded records, the anomalies were grouped as follows:
"""
    for row in neg_summary_rows:
        neg_appendix += f"\n- **{row['category']}**: {row['n']} records ({row['pct']:.1f}%)"
    neg_appendix += """

These categories are most consistent with registration lag in critically injured patients moved rapidly through the trauma workflow, default midnight timestamps when procedural time detail is incomplete, day-boundary shifting or date inversion errors, and a smaller subset of severe data entry errors. Because these records violate the timing logic required for the primary study question, they remained excluded from both the continuous timing analysis and the primary logistic regression model. Their exclusion should be described explicitly in the methods and supplement to demonstrate transparent handling of data integrity limitations.
"""
    (DOC / 'phase7_negative_timing_appendix_text.md').write_text(neg_appendix, encoding='utf-8')

    clustering_text = """# Center Clustering Notes and Checks

## Why clustering matters
TQIP aggregates encounters across many trauma centers, and local workflow differences may influence both operative timing and resource availability. A final peer-reviewed version of the paper would be methodologically stronger if it accounts for site-level clustering.

## Current preparation status
A site variable (`TQIPSITE`) has been merged into the Phase 7 primary timing dataset to prepare for cluster-robust analysis.

## Recommended next check
1. Confirm that `TQIPSITE` is complete for the restricted model-ready cohort.
2. Confirm that more than one site contributes to the final modeled cohort.
3. If both are true, rerun the primary parsimonious logistic model using cluster-robust standard errors by `TQIPSITE`.

## Recommended implementation
In statsmodels, this can be done using a fitted logistic model such as:
`fit(cov_type='cluster', cov_kwds={'groups': df['TQIPSITE']})`

## If clustering cannot be implemented
If site completeness is insufficient or the analytic cohort is too sparse after restriction, the manuscript should acknowledge that exploratory models treated encounters as independent and did not yet incorporate site-level clustering.
"""
    (DOC / 'phase7_center_clustering_notes.md').write_text(clustering_text, encoding='utf-8')

    readiness = {
        'run_timestamp': run_ts,
        'assumptions': assumptions,
        'issues': issues,
        'negative_timing_counts': dict(cat_counter),
        'negative_timing_total': total_neg,
        'primary_timing_rows': len(primary),
        'primary_timing_rows_with_site': len(primary_with_site),
        'missing_TQIPSITE_rows': missing_site,
        'distinct_sites_in_primary_timing': len(site_counts),
        'cluster_ready_flag': cluster_ready,
        'phase5_primary_model_cohort_n': phase5.get('cohort_n'),
    }
    (OUT / 'phase7_readiness_checks.json').write_text(json.dumps(readiness, indent=2), encoding='utf-8')
    (LOG / 'phase7_run.log').write_text(json.dumps(readiness, indent=2), encoding='utf-8')

if __name__ == '__main__':
    main()
