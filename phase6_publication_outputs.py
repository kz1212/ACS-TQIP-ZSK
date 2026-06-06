#!/usr/bin/env python3
import csv, json, math
from pathlib import Path
from datetime import datetime

PHASE3 = Path('/Users/Zaid/Desktop/tqip_ocular_study_phase3/outputs')
PHASE4 = Path('/Users/Zaid/Desktop/tqip_ocular_study_phase4/outputs')
WORK = Path('/Users/Zaid/Desktop/tqip_ocular_study_phase6')
OUT = WORK / 'outputs'
RAW = WORK / 'raw_tables'
LOG = WORK / 'logs'
DOC = WORK / 'docs'


def load_json(path):
    return json.loads(Path(path).read_text())


def write_csv(path, rows, fieldnames=None):
    if fieldnames is None:
        keys = []
        seen = set()
        for row in rows:
            for k in row.keys():
                if k not in seen:
                    seen.add(k)
                    keys.append(k)
        fieldnames = keys
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        w.writeheader()
        for row in rows:
            w.writerow(row)


def fmt_num(x, digits=1):
    if x is None:
        return 'NA'
    if isinstance(x, str):
        return x
    if isinstance(x, int):
        return str(x)
    return f"{x:.{digits}f}"


def fmt_med_iqr(obj, digits=1):
    if not obj or obj.get('median') is None:
        return 'NA'
    return f"{fmt_num(obj['median'], digits)} ({fmt_num(obj['iqr_q1'], digits)}–{fmt_num(obj['iqr_q3'], digits)})"


def fmt_n_pct(pos, total):
    if total in (None, 0):
        return 'NA'
    return f"{pos} ({100.0*pos/total:.1f}%)"


def main():
    run_ts = datetime.now().isoformat()
    issues = []
    assumptions = []

    p3 = load_json(PHASE3 / 'phase3_summary.json')
    p4 = load_json(PHASE4 / 'phase4_descriptive_summary.json')

    cohort_sizes = p4['cohort_sizes']
    t1 = p4['table1']
    timing = p4['timing_summary']

    # Table 1 raw companion
    overall = t1['model_ready_restricted']
    orbital = t1['orbital_adnexal']
    mixed = t1['mixed_emergent_priority']
    emergent = t1['emergent_ocular']
    
    table1_rows = []
    def add_numeric(label, key, digits=1):
        table1_rows.append({
            'variable': label,
            'overall_primary_model_ready': fmt_med_iqr(overall['numeric'][key], digits),
            'orbital_adnexal': fmt_med_iqr(orbital['numeric'][key], digits),
            'mixed_emergent_priority': fmt_med_iqr(mixed['numeric'][key], digits),
            'emergent_ocular_descriptive': fmt_med_iqr(emergent['numeric'][key], digits),
            'type': 'numeric_median_iqr',
            'raw_overall_n_nonmissing': overall['numeric'][key]['n_nonmissing'],
            'raw_orbital_n_nonmissing': orbital['numeric'][key]['n_nonmissing'],
            'raw_mixed_n_nonmissing': mixed['numeric'][key]['n_nonmissing'],
            'raw_emergent_n_nonmissing': emergent['numeric'][key]['n_nonmissing'],
        })
    def add_binary(label, key):
        table1_rows.append({
            'variable': label,
            'overall_primary_model_ready': fmt_n_pct(overall['binary'][key]['positive_n'], overall['binary'][key]['n']),
            'orbital_adnexal': fmt_n_pct(orbital['binary'][key]['positive_n'], orbital['binary'][key]['n']),
            'mixed_emergent_priority': fmt_n_pct(mixed['binary'][key]['positive_n'], mixed['binary'][key]['n']),
            'emergent_ocular_descriptive': fmt_n_pct(emergent['binary'][key]['positive_n'], emergent['binary'][key]['n']),
            'type': 'binary_n_pct',
            'raw_overall_positive_n': overall['binary'][key]['positive_n'],
            'raw_orbital_positive_n': orbital['binary'][key]['positive_n'],
            'raw_mixed_positive_n': mixed['binary'][key]['positive_n'],
            'raw_emergent_positive_n': emergent['binary'][key]['positive_n'],
        })

    add_numeric('Age, years', 'age', 1)
    add_numeric('Injury Severity Score', 'iss', 1)
    add_numeric('Arrival to first qualifying procedure, hours', 'elapsed_hours_to_first_px', 1)
    add_numeric('Systolic blood pressure', 'sbp', 1)
    add_numeric('Heart rate', 'pulse', 1)
    add_numeric('Respiratory rate', 'rr', 1)
    add_numeric('Temperature', 'temp', 1)
    add_numeric('Pulse oximetry', 'spo2', 1)
    add_numeric('ICU length of stay, days', 'iculos', 1)
    add_numeric('Ventilator days', 'ventdays', 1)
    add_numeric('Hospital length of stay, days', 'inpatientdays', 1)
    add_numeric('Pre-existing condition count', 'preexisting_condition_count', 1)
    add_binary('AIS support present', 'ais_support')
    add_binary('Major systemic complication', 'major_systemic_complication')
    add_binary('In-hospital mortality', 'in_hospital_mortality')

    write_csv(RAW / 'table1_raw.csv', table1_rows)

    # Timing table raw companion
    timing_rows = []
    for name in ['overall_primary_timing', 'orbital_adnexal', 'mixed_emergent_priority', 'emergent_ocular', 'model_ready_restricted']:
        td = timing[name]
        timing_rows.append({
            'cohort': name,
            'n': td['n'],
            'median_hours': td['distribution']['median'],
            'q1_hours': td['distribution']['iqr_q1'],
            'q3_hours': td['distribution']['iqr_q3'],
            'mean_hours': td['distribution']['mean'],
            'min_hours': td['distribution']['min'],
            'max_hours': td['distribution']['max'],
            'lt_6h_n': td['binned_counts']['lt_6h'],
            'h6_to_12_n': td['binned_counts']['6_to_12h'],
            'h12_to_24_n': td['binned_counts']['12_to_24h'],
            'gt_24h_n': td['binned_counts']['gt_24h'],
        })
    write_csv(RAW / 'timing_summary_raw.csv', timing_rows, list(timing_rows[0].keys()))

    # Regression table raw companion
    reg_rows = []
    logit = model.get('limited_multivariable_logit', {})
    if logit:
        ci = logit.get('confidence_intervals_logodds', {})
        coef = logit.get('coefficients', {})
        pvals = logit.get('pvalues', {})
        ors = logit.get('odds_ratios', {})
        for var in coef:
            if var == 'Intercept':
                continue
            lcl = math.exp(ci['0'][var]) if '0' in ci and var in ci['0'] else None
            ucl = math.exp(ci['1'][var]) if '1' in ci and var in ci['1'] else None
            reg_rows.append({
                'model': 'limited_multivariable_logit',
                'outcome': f'prolonged delay > median ({median_cut:.2f} hours)',
                'variable': var,
                'odds_ratio': ors.get(var),
                'ci_lower': lcl,
                'ci_upper': ucl,
                'p_value': pvals.get(var),
                'coefficient_logodds': coef.get(var),
                'n_complete_case': logit.get('n')
            })
    ols = model.get('exploratory_log_elapsed_ols', {})
    if ols:
        for var, coef in ols.get('coefficients', {}).items():
            if var == 'Intercept':
                continue
            reg_rows.append({
                'model': 'exploratory_log_elapsed_ols',
                'outcome': 'log(arrival to first qualifying procedure hours + 1)',
                'variable': var,
                'odds_ratio': '',
                'ci_lower': '',
                'ci_upper': '',
                'p_value': ols.get('pvalues', {}).get(var),
                'coefficient_logodds': coef,
                'n_complete_case': ols.get('n')
            })
    write_csv(RAW / 'regression_results_raw.csv', reg_rows, list(reg_rows[0].keys()))


## Statistical Analysis
    (OUT / 'publication_methods.md').write_text(methods_text, encoding='utf-8')

    # Clinician-readable results
    methods_ready_n = cohort_sizes['model_ready_restricted']
    emergent_n = cohort_sizes['emergent_descriptive_only']
    overall_timing = timing['model_ready_restricted']['distribution']
    lt6 = timing['model_ready_restricted']['binned_counts']['lt_6h']
    gt24 = timing['model_ready_restricted']['binned_counts']['gt_24h']
    results_text = f"""# Publication-Style Results

## Cohort Assembly and Analysis Population
The locked operable cohort contained {cohort_sizes['locked_operable']} severely injured encounters meeting the final diagnosis and procedure criteria. After restricting to direct arrivals with valid non-negative timing for the primary analysis, the primary timing cohort contained {cohort_sizes['primary_timing']} encounters. Consistent with prior face-validity review, the restricted model-ready cohort contained {methods_ready_n} encounters, almost all of which were orbital/adnexal or mixed emergent-priority cases, whereas only {emergent_n} emergent ocular cases remained available for descriptive reporting.

## Descriptive Cohort Characteristics
In the restricted model-ready cohort, the median age was {fmt_num(overall['numeric']['age']['median'],1)} years and the median Injury Severity Score was {fmt_num(overall['numeric']['iss']['median'],1)}. The median time from arrival to first qualifying ocular/orbital operative intervention was {fmt_num(overall_timing['median'],1)} hours (IQR {fmt_num(overall_timing['iqr_q1'],1)}–{fmt_num(overall_timing['iqr_q3'],1)}). A total of {lt6} encounters occurred within 6 hours of arrival, whereas {gt24} occurred more than 24 hours after arrival.

## Exploratory Modeling of Prolonged Delay
Using a median-based prolonged-delay definition (> {median_cut:.2f} hours), the first-pass restricted multivariable model suggested that higher Injury Severity Score and AIS-supported injury classification were associated with greater odds of prolonged delay, whereas older age showed a small inverse association with prolonged delay. Specifically, the odds ratio for Injury Severity Score was {fmt_num(logit.get('odds_ratios',{}).get('iss'),3)} and the odds ratio for AIS support was {fmt_num(logit.get('odds_ratios',{}).get('ais_support_num'),3)}. These estimates should be interpreted cautiously as exploratory signals used to refine the final manuscript-level model specification.

## Secondary Clinical Context
Major systemic complications and in-hospital mortality were retained for descriptive context only. Because delayed ocular/orbital intervention in this dataset is likely to reflect competing injury priorities and survivorship effects rather than act as a direct causal driver of systemic deterioration, these secondary outcomes should not be interpreted causally in the current analysis phase.
"""
    (OUT / 'publication_results.md').write_text(results_text, encoding='utf-8')

    # Manuscript-style tables in markdown
    table1_md = ['# Table 1. Baseline Characteristics of the Restricted Primary Timing Cohort', '', '| Variable | Overall model-ready cohort | Orbital/adnexal | Mixed emergent-priority | Emergent ocular (descriptive) |', '|---|---:|---:|---:|---:|']
    for row in table1_rows:
        table1_md.append(f"| {row['variable']} | {row['overall_primary_model_ready']} | {row['orbital_adnexal']} | {row['mixed_emergent_priority']} | {row['emergent_ocular_descriptive']} |")
    (OUT / 'table1_manuscript.md').write_text('\n'.join(table1_md), encoding='utf-8')

    timing_md = ['# Table 2. Timing of First Qualifying Ocular/Orbital Procedure', '', '| Cohort | N | Median hours (IQR) | <6 h | 6–12 h | 12–24 h | >24 h |', '|---|---:|---:|---:|---:|---:|---:|']
    for row in timing_rows:
        med_iqr = f"{fmt_num(row['median_hours'],1)} ({fmt_num(row['q1_hours'],1)}–{fmt_num(row['q3_hours'],1)})"
        timing_md.append(f"| {row['cohort']} | {row['n']} | {med_iqr} | {row['lt_6h_n']} | {row['h6_to_12_n']} | {row['h12_to_24_n']} | {row['gt_24h_n']} |")
    (OUT / 'table2_timing_manuscript.md').write_text('\n'.join(timing_md), encoding='utf-8')

    reg_md = ['# Table 3. Exploratory Restricted Modeling Results', '', '| Model | Variable | Effect estimate | 95% CI | P value | N |', '|---|---|---:|---:|---:|---:|']
    for row in reg_rows:
        if row['model'] == 'limited_multivariable_logit':
            eff = fmt_num(row['odds_ratio'],3)
            ci_txt = f"{fmt_num(row['ci_lower'],3)}–{fmt_num(row['ci_upper'],3)}"
        else:
            eff = fmt_num(row['coefficient_logodds'],3)
            ci_txt = 'See raw companion'
        reg_md.append(f"| {row['model']} | {row['variable']} | {eff} | {ci_txt} | {fmt_num(row['p_value'],4)} | {row['n_complete_case']} |")
    (OUT / 'table3_regression_manuscript.md').write_text('\n'.join(reg_md), encoding='utf-8')

    # Technical appendix/supplement
    appendix_text = f"""# Technical Appendix and Reproducibility Supplement


## Data Lineage
- Phase 3 locked dataset: `{PHASE3 / 'phase3_locked_operable_dataset.csv'}`
- Phase 3 primary timing dataset: `{PHASE3 / 'phase3_primary_timing_dataset.csv'}`
- Phase 3 negative timing review export: `{PHASE3 / 'phase3_negative_timing_review.csv'}`
- Phase 4 descriptive summary: `{PHASE4 / 'phase4_descriptive_summary.json'}`

## Raw Table Companions
- `raw_tables/table1_raw.csv`
- `raw_tables/timing_summary_raw.csv`
- `raw_tables/regression_results_raw.csv`


"""
    (OUT / 'technical_appendix_and_supplement.md').write_text(appendix_text, encoding='utf-8')

    # Change log
    change_log = f"""# Phase 6 Change Log

Run timestamp: {run_ts}


## Source files referenced
- {PHASE3 / 'phase3_summary.json'}
- {PHASE4 / 'phase4_descriptive_summary.json'}
- {PHASE5 / 'phase5_model_summary.json'}


"""
    (DOC / 'phase6_change_log.md').write_text(change_log, encoding='utf-8')

    final_summary = {
        'run_timestamp': run_ts,
        'assumptions': assumptions,
        'issues': issues,
        'outputs': {
            'methods': str(OUT / 'publication_methods.md'),
            'results': str(OUT / 'publication_results.md'),
            'table1_manuscript': str(OUT / 'table1_manuscript.md'),
            'table2_timing_manuscript': str(OUT / 'table2_timing_manuscript.md'),
            'table3_regression_manuscript': str(OUT / 'table3_regression_manuscript.md'),
            'technical_appendix': str(OUT / 'technical_appendix_and_supplement.md'),
            'table1_raw': str(RAW / 'table1_raw.csv'),
            'timing_raw': str(RAW / 'timing_summary_raw.csv'),
            'regression_raw': str(RAW / 'regression_results_raw.csv'),
        }
    }
    (OUT / 'phase6_summary.json').write_text(json.dumps(final_summary, indent=2), encoding='utf-8')
    (LOG / 'phase6_run.log').write_text(json.dumps(final_summary, indent=2), encoding='utf-8')

if __name__ == '__main__':
    main()
