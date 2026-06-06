#!/usr/bin/env python3
import csv, json, math
from pathlib import Path
from datetime import datetime
from collections import Counter

PHASE4 = Path('/Users/Zaid/Desktop/tqip_ocular_study_phase4/outputs')
PHASE3 = Path('/Users/Zaid/Desktop/tqip_ocular_study_phase3/outputs')
WORK = Path('/Users/Zaid/Desktop/tqip_ocular_study_phase5')
OUT = WORK / 'outputs'
LOG = WORK / 'logs'
DOC = WORK / 'docs'

# Try to use statsmodels if available; otherwise fallback to descriptive quantile groups.
try:
    import pandas as pd
    import statsmodels.api as sm
    import statsmodels.formula.api as smf
    HAVE_SM = True
except Exception:
    HAVE_SM = False


def load_csv(path):
    with open(path, newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def to_float(x):
    try:
        if x in ('', None):
            return None
        return float(x)
    except Exception:
        return None


def to_int(x):
    try:
        if x in ('', None):
            return None
        return int(float(x))
    except Exception:
        return None


def prep_rows(rows):
    out = []
    for r in rows:
        rr = dict(r)
        for v in ['age','iss','elapsed_hours_to_first_px','sbp','pulse','rr','temp','spo2','iculos','ventdays','inpatientdays','preexisting_condition_count']:
            rr[v] = to_float(rr.get(v))
        rr['gcsmotor_num'] = to_float(rr.get('gcsmotor'))
        rr['ais_support_num'] = to_int(rr.get('ais_support'))
        rr['major_systemic_complication_num'] = to_int(rr.get('major_systemic_complication'))
        rr['in_hospital_mortality_num'] = to_int(rr.get('in_hospital_mortality'))
        rr['hmrrhg_present'] = 1 if rr.get('hmrrhgtype') not in ('', None, '1') else 0
        rr['angiography_present'] = 1 if rr.get('angiography') not in ('', None, '1') else 0
        rr['mixed_stratum'] = 1 if rr.get('stratum') == 'mixed_emergent_priority' else 0
        out.append(rr)
    return out


def median(vals):
    vals = sorted(v for v in vals if v is not None)
    if not vals:
        return None
    return vals[len(vals)//2]


def quantile_groups(vals):
    s = sorted(v for v in vals if v is not None)
    if len(s) < 4:
        return None
    return (s[len(s)//4], s[len(s)//2], s[(3*len(s))//4])


def main():
    run_ts = datetime.now().isoformat()
    issues = []
    assumptions = [
        'Phase 5 uses the restricted model-ready cohort from the direct-arrival primary timing dataset.',
        'Emergent ocular cases are not included in primary modeling and remain descriptive/sensitivity only.',
        'Given observed skewness in elapsed hours, modeling is exploratory and intended to identify directionality rather than finalize a publication-ready inferential model.',
        'Hospital-level clustering is not modeled in this phase.',
    ]

    primary = load_csv(PHASE3 / 'phase3_primary_timing_dataset.csv')
    model_rows = [r for r in primary if r['stratum'] in {'orbital_adnexal', 'mixed_emergent_priority'}]
    model_rows = prep_rows(model_rows)

    if len(model_rows) == 0:
        raise RuntimeError('No model-ready rows available.')

    elapsed_vals = [r['elapsed_hours_to_first_px'] for r in model_rows if r['elapsed_hours_to_first_px'] is not None]
    q = quantile_groups(elapsed_vals)
    if q is None:
        issues.append('Could not compute stable quantile groups; sample too small.')
        q1 = q2 = q3 = None
    else:
        q1, q2, q3 = q

    # Create a binary prolonged delay endpoint for safer first-pass modeling.
    # Use > median as the primary binary outcome.
    med = median(elapsed_vals)
    for r in model_rows:
        eh = r['elapsed_hours_to_first_px']
        r['prolonged_delay'] = 1 if (eh is not None and med is not None and eh > med) else 0
        r['log_elapsed'] = math.log(eh + 1.0) if eh is not None and eh >= 0 else None

    # Descriptive univariable summaries by prolonged delay status.
    by_delay = {0: [], 1: []}
    for r in model_rows:
        by_delay[r['prolonged_delay']].append(r)

    univariable_descriptives = {}
    for var in ['age','iss','sbp','pulse','rr','temp','spo2','gcsmotor_num','preexisting_condition_count']:
        univariable_descriptives[var] = {
            'delay0_median': median([r[var] for r in by_delay[0]]),
            'delay1_median': median([r[var] for r in by_delay[1]]),
            'n_nonmissing': sum(1 for r in model_rows if r[var] is not None),
        }
    for var in ['mixed_stratum','ais_support_num','hmrrhg_present','angiography_present','major_systemic_complication_num','in_hospital_mortality_num']:
        d0 = by_delay[0]
        d1 = by_delay[1]
        univariable_descriptives[var] = {
            'delay0_pct_positive': (100.0*sum(r[var]==1 for r in d0)/len(d0) if d0 else None),
            'delay1_pct_positive': (100.0*sum(r[var]==1 for r in d1)/len(d1) if d1 else None),
            'n_nonmissing': len(model_rows),
        }

    model_results = {'statsmodels_available': HAVE_SM}

    if HAVE_SM:
        df = pd.DataFrame(model_rows)
        # limited complete-case model with variables that had acceptable completeness
        model_vars = ['prolonged_delay','age','iss','sbp','pulse','spo2','gcsmotor_num','mixed_stratum','ais_support_num','hmrrhg_present','angiography_present']
        dff = df[model_vars].dropna().copy()
        model_results['complete_case_n'] = int(len(dff))
        if len(dff) < 200:
            issues.append('Complete-case multivariable sample is smaller than ideal for a more stable first-pass model.')
        try:
            fit = smf.logit('prolonged_delay ~ age + iss + sbp + pulse + spo2 + gcsmotor_num + mixed_stratum + ais_support_num + hmrrhg_present + angiography_present', data=dff).fit(disp=False)
            params = fit.params.to_dict()
            conf = fit.conf_int().to_dict()
            pvals = fit.pvalues.to_dict()
            ors = {k: math.exp(v) for k,v in params.items()}
            model_results['limited_multivariable_logit'] = {
                'n': int(len(dff)),
                'median_delay_cutpoint_hours': med,
                'odds_ratios': ors,
                'coefficients': params,
                'pvalues': pvals,
                'confidence_intervals_logodds': conf,
            }
        except Exception as e:
            issues.append(f'Statsmodels logistic model failed: {e}')

        # exploratory OLS on log elapsed hours
        dff2 = df[['log_elapsed','age','iss','sbp','pulse','spo2','gcsmotor_num','mixed_stratum','ais_support_num','hmrrhg_present','angiography_present']].dropna().copy()
        model_results['complete_case_n_log_elapsed'] = int(len(dff2))
        try:
            fit2 = smf.ols('log_elapsed ~ age + iss + sbp + pulse + spo2 + gcsmotor_num + mixed_stratum + ais_support_num + hmrrhg_present + angiography_present', data=dff2).fit()
            model_results['exploratory_log_elapsed_ols'] = {
                'n': int(len(dff2)),
                'coefficients': fit2.params.to_dict(),
                'pvalues': fit2.pvalues.to_dict(),
                'r_squared': float(fit2.rsquared),
            }
        except Exception as e:
            issues.append(f'Statsmodels OLS model failed: {e}')
    else:
        issues.append('statsmodels/pandas unavailable; only descriptive univariable summaries were produced.')

    recommendation = 'restricted_modeling_completed'
    recommendation_text = (
        'A first-pass restricted modeling scaffold has been completed. Results should be treated as exploratory and used to refine the final manuscript-level model specification, not as the final inferential analysis.'
    )

    out = {
        'run_timestamp': run_ts,
        'assumptions': assumptions,
        'issues': issues,
        'cohort_n': len(model_rows),
        'median_elapsed_hours_cutpoint': med,
        'quantile_markers': {'q1': q1, 'median': q2, 'q3': q3} if q is not None else None,
        'univariable_descriptives_by_prolonged_delay': univariable_descriptives,
        'model_results': model_results,
        'recommendation': recommendation,
        'recommendation_text': recommendation_text,
    }

    (OUT / 'phase5_model_summary.json').write_text(json.dumps(out, indent=2), encoding='utf-8')
    with open(OUT / 'phase5_report.txt', 'w', encoding='utf-8') as f:
        f.write('PHASE 5 RESTRICTED MODELING PLAN AND FIRST-PASS MODELS REPORT\n')
        f.write(f'Run timestamp: {run_ts}\n\n')
        f.write('This phase created a restricted modeling scaffold and generated first-pass exploratory models for prolonged delay in the direct-arrival orbital/adnexal-dominant cohort.\n\n')
        f.write(f'- cohort_n: {len(model_rows)}\n')
        f.write(f'- median_elapsed_hours_cutpoint: {med}\n')
        f.write(f'- quantile_markers: {out["quantile_markers"]}\n\n')
        f.write('UNIVARIABLE DESCRIPTIVES BY PROLONGED DELAY STATUS\n')
        for k,v in univariable_descriptives.items():
            f.write(f'- {k}: {v}\n')
        f.write('\nMODEL RESULTS\n')
        f.write(json.dumps(model_results, indent=2))
        f.write('\n\nMAJOR ISSUES / NOTES\n')
        if issues:
            for item in issues:
                f.write(f'- {item}\n')
        else:
            f.write('- No major unexpected issues recorded in Phase 5.\n')
        f.write('\nRECOMMENDATION\n')
        f.write(f'- {recommendation}: {recommendation_text}\n')

    (DOC / 'phase5_modeling_note.txt').write_text(recommendation_text + '\n\n' + '\n'.join(issues), encoding='utf-8')
    (LOG / 'phase5_run.log').write_text(json.dumps({'run_timestamp': run_ts, 'issues': issues, 'recommendation': recommendation}, indent=2), encoding='utf-8')

if __name__ == '__main__':
    main()
