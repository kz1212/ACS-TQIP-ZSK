#!/usr/bin/env python3
import csv, json, math, statistics
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime

PHASE3 = Path('/Users/___/Desktop/tqip_ocular_study_phase3/outputs')
PHASE35 = Path('/Users/___/Desktop/tqip_ocular_study_phase35/outputs')
WORK = Path('/Users/___/Desktop/tqip_ocular_study_phase4')
OUT = WORK / 'outputs'
LOG = WORK / 'logs'
DOC = WORK / 'docs'


def load_csv(path):
    with open(path, newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def try_float(x):
    try:
        if x in (None, ''):
            return None
        return float(x)
    except Exception:
        return None


def summarize_numeric(rows, var):
    vals = [try_float(r[var]) for r in rows]
    vals = [v for v in vals if v is not None]
    if not vals:
        return {'n_nonmissing': 0, 'median': None, 'iqr_q1': None, 'iqr_q3': None, 'mean': None, 'min': None, 'max': None}
    vals_sorted = sorted(vals)
    n = len(vals_sorted)
    q1 = vals_sorted[n//4]
    med = vals_sorted[n//2]
    q3 = vals_sorted[(3*n)//4]
    return {
        'n_nonmissing': n,
        'median': med,
        'iqr_q1': q1,
        'iqr_q3': q3,
        'mean': sum(vals_sorted)/n,
        'min': vals_sorted[0],
        'max': vals_sorted[-1],
    }


def summarize_binary(rows, var, positive_values={'1'}):
    n = len(rows)
    pos = sum(1 for r in rows if r.get(var, '') in positive_values)
    return {'n': n, 'positive_n': pos, 'positive_pct': (100.0*pos/n if n else None)}


def summarize_categorical(rows, var, top_n=10):
    c = Counter(r.get(var, '') for r in rows)
    return [{'level': k, 'n': v, 'pct': (100.0*v/len(rows) if rows else None)} for k,v in c.most_common(top_n)]


def completeness(rows, vars_list):
    out = []
    n = len(rows)
    for var in vars_list:
        nonmiss = sum(1 for r in rows if r.get(var, '') not in ('', None))
        out.append({'variable': var, 'n_nonmissing': nonmiss, 'pct_nonmissing': (100.0*nonmiss/n if n else None)})
    return out


def main():
    run_ts = datetime.now().isoformat()
    issues = []
    assumptions = [
        'Phase 4 uses the Phase 3 primary timing dataset as the main restricted analysis-ready cohort.',
        'Primary timing cohort excludes negative elapsed-time records and is direct-arrival only.',
        'Given Phase 3.5 findings, orbital/adnexal-dominant reporting is emphasized and emergent ocular counts are interpreted descriptively.',
    ]

    primary = load_csv(PHASE3 / 'phase3_primary_timing_dataset.csv')
    locked = load_csv(PHASE3 / 'phase3_locked_operable_dataset.csv')
    face = json.loads((PHASE35 / 'phase35_face_validity_summary.json').read_text())

    # Restricted modeling-ready cohort: orbital/adnexal + mixed only, keep emergent summarized separately.
    model_ready = [r for r in primary if r['stratum'] in {'orbital_adnexal', 'mixed_emergent_priority'}]
    emergent_desc = [r for r in primary if r['stratum'] == 'emergent_ocular']

    # Table 1 overall and by stratum
    strata = {
        'overall_primary_timing': primary,
        'orbital_adnexal': [r for r in primary if r['stratum'] == 'orbital_adnexal'],
        'mixed_emergent_priority': [r for r in primary if r['stratum'] == 'mixed_emergent_priority'],
        'emergent_ocular': emergent_desc,
        'model_ready_restricted': model_ready,
    }

    numeric_vars = ['age', 'iss', 'elapsed_hours_to_first_px', 'sbp', 'pulse', 'rr', 'temp', 'spo2', 'iculos', 'ventdays', 'inpatientdays', 'preexisting_condition_count']
    binary_vars = ['ais_support', 'major_systemic_complication', 'in_hospital_mortality']
    categorical_vars = ['sex', 'ethnicity', 'payer', 'gcsmotor', 'hospdisp', 'eddisp', 'first_px_code', 'stratum']

    table1 = {}
    for name, rows in strata.items():
        table1[name] = {
            'n_rows': len(rows),
            'numeric': {v: summarize_numeric(rows, v) for v in numeric_vars},
            'binary': {v: summarize_binary(rows, v) for v in binary_vars},
            'categorical_top': {v: summarize_categorical(rows, v, top_n=10) for v in categorical_vars},
        }

    # Timing summaries
    timing_bins = [
        ('lt_6h', lambda x: x is not None and x < 6),
        ('6_to_12h', lambda x: x is not None and 6 <= x < 12),
        ('12_to_24h', lambda x: x is not None and 12 <= x < 24),
        ('gt_24h', lambda x: x is not None and x >= 24),
    ]
    timing_summary = {}
    for name, rows in strata.items():
        vals = [try_float(r['elapsed_hours_to_first_px']) for r in rows]
        vals = [v for v in vals if v is not None]
        counts = {}
        for label, fn in timing_bins:
            counts[label] = sum(1 for v in vals if fn(v))
        timing_summary[name] = {
            'n': len(vals),
            'distribution': summarize_numeric(rows, 'elapsed_hours_to_first_px'),
            'binned_counts': counts,
        }

    # Covariate completeness for model-ready cohort
    candidate_covariates = ['age', 'sex', 'ethnicity', 'payer', 'iss', 'sbp', 'pulse', 'rr', 'temp', 'spo2', 'gcsmotor', 'totalgcs', 'prehosp_arrest', 'highestactivation', 'hmrrhgtype', 'angiography', 'preexisting_condition_count', 'ais_support']
    completeness_model_ready = completeness(model_ready, candidate_covariates)

    # First-procedure frequencies in model-ready cohort
    first_px_model_ready = summarize_categorical(model_ready, 'first_px_code', top_n=25)

    # Readiness assessment
    if len(model_ready) < 500:
        issues.append('Model-ready restricted cohort is smaller than expected and may constrain multivariable complexity.')
    if len(emergent_desc) < 10:
        issues.append('Emergent ocular cases remain too sparse for stable primary modeling and should remain descriptive/sensitivity only.')
    nonmiss_gcsmotor = next((x['pct_nonmissing'] for x in completeness_model_ready if x['variable']=='gcsmotor'), None)
    if nonmiss_gcsmotor is not None and nonmiss_gcsmotor < 70:
        issues.append('GCS motor completeness is limited and may complicate planned neurologic adjustment.')

    recommendation = 'ready_for_restricted_modeling'
    recommendation_text = ('ready')

    out = {
        'run_timestamp': run_ts,
        'assumptions': assumptions,
        'issues': issues,
        'source_face_validity_recommendation': face.get('recommendation'),
        'cohort_sizes': {
            'primary_timing': len(primary),
            'model_ready_restricted': len(model_ready),
            'emergent_descriptive_only': len(emergent_desc),
            'locked_operable': len(locked),
        },
        'table1': table1,
        'timing_summary': timing_summary,
        'covariate_completeness_model_ready': completeness_model_ready,
        'top_first_px_model_ready': first_px_model_ready,
        'recommendation': recommendation,
        'recommendation_text': recommendation_text,
    }

    (OUT / 'phase4_descriptive_summary.json').write_text(json.dumps(out, indent=2), encoding='utf-8')
    with open(OUT / 'phase4_report.txt', 'w', encoding='utf-8') as f:
        f.write('PHASE 4 ANALYSIS-READY DESCRIPTIVE TABLES AND MODELING SETUP REPORT\n')
        f.write(f'Run timestamp: {run_ts}\n\n')
        f.write('This phase generated analysis-ready descriptive summaries from the restricted primary timing cohort and assessed readiness for modeling.\n\n')
        f.write('COHORT SIZES\n')
        for k,v in out['cohort_sizes'].items():
            f.write(f'- {k}: {v}\n')
        f.write('\nTIMING SUMMARY (MODEL-READY RESTRICTED COHORT)\n')
        f.write(f"- {timing_summary['model_ready_restricted']}\n")
        f.write('\nTOP FIRST-PROCEDURE CODES (MODEL-READY RESTRICTED COHORT)\n')
        for row in first_px_model_ready[:20]:
            f.write(f"- {row['level']}: n={row['n']} pct={row['pct']:.2f}\n")
        f.write('\nCOVARIATE COMPLETENESS (MODEL-READY COHORT)\n')
        for row in completeness_model_ready:
            f.write(f"- {row['variable']}: n_nonmissing={row['n_nonmissing']} pct_nonmissing={row['pct_nonmissing']:.2f}\n")
        f.write('\nMAJOR ISSUES / NOTES\n')
        if issues:
            for item in issues:
                f.write(f'- {item}\n')
        else:
            f.write('- No major unexpected issues recorded in Phase 4.\n')
        f.write('\nRECOMMENDATION\n')
        f.write(f'- {recommendation}: {recommendation_text}\n')

    (DOC / 'phase4_modeling_ready_note.txt').write_text(recommendation_text + '\n\n' + '\n'.join(issues), encoding='utf-8')
    (LOG / 'phase4_run.log').write_text(json.dumps({'run_timestamp': run_ts, 'issues': issues, 'recommendation': recommendation}, indent=2), encoding='utf-8')

if __name__ == '__main__':
    main()
