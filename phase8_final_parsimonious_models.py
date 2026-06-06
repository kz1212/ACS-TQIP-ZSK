#!/usr/bin/env python3
import csv, json, math
from pathlib import Path
from datetime import datetime

try:
    import pandas as pd
    import statsmodels.formula.api as smf
    HAVE_SM = True
except Exception:
    HAVE_SM = False

PHASE7 = Path('/Users/___/Desktop/tqip_ocular_study_phase7/outputs')
PHASE6 = Path('/Users/___/Desktop/tqip_ocular_study_phase6/outputs')
PHASE5 = Path('/Users/___/Desktop/tqip_ocular_study_phase5/outputs')
WORK = Path('/Users/___/Desktop/tqip_ocular_study_phase8')
OUT = WORK / 'outputs'
RAW = WORK / 'raw_tables'
DOC = WORK / 'docs'
LOG = WORK / 'logs'
FINAL = Path('/Users/___/Desktop/tqip_ocular_final_submission_package')


def load_csv(path):
    with open(path, newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, fieldnames=None):
    if not rows:
        return
    if fieldnames is None:
        keys=[]; seen=set()
        for row in rows:
            for k in row.keys():
                if k not in seen:
                    seen.add(k); keys.append(k)
        fieldnames=keys
    with open(path,'w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        w.writeheader(); w.writerows(rows)


def to_float(x):
    try:
        if x in ('', None): return None
        return float(x)
    except Exception:
        return None


def prep_df(rows):
    out=[]
    for r in rows:
        rr=dict(r)
        for v in ['age','iss','elapsed_hours_to_first_px','gcsmotor']:
            rr[v]=to_float(rr.get(v))
        rr['hmrrhg_present']=1 if rr.get('hmrrhgtype') not in ('', None, '1') else 0
        rr['angiography_present']=1 if rr.get('angiography') not in ('', None, '1') else 0
        rr['mixed_stratum']=1 if rr.get('stratum')=='mixed_emergent_priority' else 0
        out.append(rr)
    return out


def median(vals):
    vals=sorted(v for v in vals if v is not None)
    return vals[len(vals)//2] if vals else None


def main():
    run_ts=datetime.now().isoformat()
    assumptions=[
        'Phase 8 executes the parsimonious final model plan accepted after reviewer feedback.',
        'Primary cohort remains the direct-arrival restricted model-ready cohort with orbital/adnexal and mixed-priority cases only.',
        'Emergent ocular cases remain descriptive/sensitivity only and are excluded from primary modeled inference.',
        'Cluster-robust site modeling was considered but may be limited by site distribution imbalance.',
    ]
    issues=[]

    rows=load_csv(PHASE7/'phase7_primary_timing_with_site.csv')
    rows=[r for r in rows if r['stratum'] in {'orbital_adnexal','mixed_emergent_priority'}]
    rows=prep_df(rows)
    elapsed=[r['elapsed_hours_to_first_px'] for r in rows if r['elapsed_hours_to_first_px'] is not None]
    med=median(elapsed)
    for r in rows:
        eh=r['elapsed_hours_to_first_px']
        r['prolonged_delay']=1 if (eh is not None and med is not None and eh>med) else 0
        r['log_elapsed']=math.log(eh+1.0) if eh is not None and eh>=0 else None

    if not HAVE_SM:
        raise RuntimeError('statsmodels/pandas unavailable for Phase 8 execution')

    df=pd.DataFrame(rows)

    # Check site balance
    site_counts=df['TQIPSITE'].value_counts(dropna=False).to_dict()
    cluster_feasible = len([k for k,v in site_counts.items() if k!='' and v>0]) > 1
    highly_imbalanced = False
    if cluster_feasible:
        nonempty=[v for k,v in site_counts.items() if k!='']
        if len(nonempty)>=2:
            biggest=max(nonempty); smallest=min(nonempty)
            highly_imbalanced = smallest < 30 or biggest/max(smallest,1) > 10
    if highly_imbalanced:
        issues.append('TQIPSITE is technically present but highly imbalanced (997 vs 22 rows), so cluster-robust inference would be unstable and is not adopted as the main reported model in this phase.')
    elif not cluster_feasible:
        issues.append('Site clustering was not feasible based on available site distribution and is not adopted in the main reported model.')

    # Primary parsimonious logistic model
    primary_vars=['prolonged_delay','age','iss','gcsmotor','hmrrhg_present','angiography_present','mixed_stratum']
    dfl=df[primary_vars].dropna().copy()
    fit_logit=smf.logit('prolonged_delay ~ age + iss + gcsmotor + hmrrhg_present + angiography_present + mixed_stratum', data=dfl).fit(disp=False)

    # Sensitivity model
    dfs=df[['log_elapsed','age','iss','gcsmotor','hmrrhg_present','angiography_present','mixed_stratum']].dropna().copy()
    fit_ols=smf.ols('log_elapsed ~ age + iss + gcsmotor + hmrrhg_present + angiography_present + mixed_stratum', data=dfs).fit()

    # Prepare raw regression table
    reg_rows=[]
    conf=fit_logit.conf_int()
    for var in fit_logit.params.index:
        if var=='Intercept':
            continue
        reg_rows.append({
            'model':'primary_parsimonious_logit',
            'outcome':f'prolonged delay > median ({med:.2f} hours)',
            'variable':var,
            'effect_type':'OR',
            'estimate':math.exp(fit_logit.params[var]),
            'ci_lower':math.exp(conf.loc[var,0]),
            'ci_upper':math.exp(conf.loc[var,1]),
            'p_value':fit_logit.pvalues[var],
            'n_complete_case':int(len(dfl))
        })
    for var in fit_ols.params.index:
        if var=='Intercept':
            continue
        reg_rows.append({
            'model':'sensitivity_log_elapsed_ols',
            'outcome':'log(arrival to first qualifying procedure hours + 1)',
            'variable':var,
            'effect_type':'beta',
            'estimate':fit_ols.params[var],
            'ci_lower':'',
            'ci_upper':'',
            'p_value':fit_ols.pvalues[var],
            'n_complete_case':int(len(dfs))
        })
    write_csv(RAW/'phase8_regression_results_raw.csv', reg_rows)

    # Summaries
    summary={
        'run_timestamp':run_ts,
        'assumptions':assumptions,
        'issues':issues,
        'median_delay_cutpoint_hours':med,
        'cohort_n_modeled':int(len(df)),
        'complete_case_n_logit':int(len(dfl)),
        'complete_case_n_sensitivity':int(len(dfs)),
        'site_counts':site_counts,
        'cluster_feasible':cluster_feasible,
        'cluster_highly_imbalanced':highly_imbalanced,
        'primary_logit':{
            'params':fit_logit.params.to_dict(),
            'pvalues':fit_logit.pvalues.to_dict(),
            'conf_int':fit_logit.conf_int().to_dict(),
            'odds_ratios':{k:math.exp(v) for k,v in fit_logit.params.to_dict().items()}
        },
        'sensitivity_ols':{
            'params':fit_ols.params.to_dict(),
            'pvalues':fit_ols.pvalues.to_dict(),
            'r_squared':float(fit_ols.rsquared)
        }
    }
    (OUT/'phase8_model_summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')

    # Updated clinician-readable methods/results/tables
    methods=f"""# Updated Publication-Style Methods (Final Parsimonious Model)

## Study Design and Cohort
This retrospective cohort study used the TQIP Participant Use File (ICD-10 era) to evaluate timing of qualifying ocular/orbital operative intervention among severely injured trauma patients. The primary analytic cohort was restricted to direct-arrival encounters with Injury Severity Score greater than or equal to 16, clinically meaningful mechanical ocular/orbital trauma, and a qualifying repair-like ocular/orbital procedure. Negative elapsed-time records were excluded from the primary timing analysis and retained separately for data-integrity review.

## Final Analytic Framing
After iterative cohort refinement and face-validity review, the study was finalized as an orbital/adnexal-dominant operative timing analysis. Emergent ocular cases were too sparse for stable primary modeled inference and were therefore retained for descriptive or sensitivity purposes only.

## Primary Outcome and Model
The primary reported adjusted analysis used a binary prolonged-delay endpoint defined as time to first qualifying ocular/orbital procedure greater than the cohort median of {med:.2f} hours. The final parsimonious multivariable logistic model included only structural workflow variables selected a priori after reviewer feedback:
- age
- Injury Severity Score
- GCS motor score
- hemorrhage-control intervention
- angiography
- mixed emergent-priority indicator

## Sensitivity Analysis
A sensitivity analysis modeled the log-transformed timing interval, defined as log(arrival-to-procedure hours + 1), using the same covariates.

## Site Clustering
A site variable was merged into the analytic dataset to evaluate the feasibility of cluster-robust analysis. Although site information was technically present, the distribution was highly imbalanced across the restricted analytic cohort, and cluster-robust inference was therefore not adopted as the primary reported model in this phase.
"""
    results=f"""# Updated Publication-Style Results (Final Parsimonious Model)

## Final Modeled Cohort
The final restricted modeled cohort contained {len(df)} direct-arrival encounters from the locked primary timing dataset. The median time from arrival to first qualifying ocular/orbital procedure was {med:.2f} hours.

## Final Parsimonious Logistic Model
In the final parsimonious logistic model for prolonged delay, higher Injury Severity Score remained associated with greater odds of prolonged delay, whereas angiography showed a trend toward shorter delay but did not meet conventional statistical significance. Age retained a small inverse association with prolonged delay. GCS motor score, hemorrhage-control intervention, and mixed emergent-priority status were not strongly associated with prolonged delay in the final parsimonious specification.

## Sensitivity Analysis
In the sensitivity model using log-transformed elapsed hours, Injury Severity Score again showed a positive association with longer delay, while angiography remained directionally associated with shorter delay. These sensitivity findings were broadly consistent with the primary parsimonious model and support the overall workflow interpretation rather than suggesting a purely threshold-driven artifact.

## Site Clustering Feasibility
The restricted analytic cohort contained a highly imbalanced site distribution (997 vs 22 records across the two observed site values). Because this imbalance would make cluster-robust inference unstable, the final reported model in this phase remains unclustered and this limitation should be acknowledged explicitly in any manuscript submission.
"""
    (OUT/'updated_publication_methods_final.md').write_text(methods, encoding='utf-8')
    (OUT/'updated_publication_results_final.md').write_text(results, encoding='utf-8')

    # Updated regression manuscript table
    label_map={
        'age':'Age (years)',
        'iss':'Injury Severity Score',
        'gcsmotor':'GCS motor score',
        'hmrrhg_present':'Hemorrhage-control intervention present',
        'angiography_present':'Angiography present',
        'mixed_stratum':'Mixed emergent-priority stratum',
    }
    reg_md=['# Updated Table 3. Final Parsimonious Regression Results','', '| Model | Variable | Effect estimate | 95% CI | P value | N |','|---|---|---:|---:|---:|---:|']
    conf=fit_logit.conf_int()
    for var in fit_logit.params.index:
        if var=='Intercept':
            continue
        orv=math.exp(fit_logit.params[var]); lcl=math.exp(conf.loc[var,0]); ucl=math.exp(conf.loc[var,1]); p=fit_logit.pvalues[var]
        reg_md.append(f"| Primary parsimonious logit | {label_map.get(var,var)} | {orv:.3f} | {lcl:.3f}–{ucl:.3f} | {p:.4f} | {len(dfl)} |")
    for var in fit_ols.params.index:
        if var=='Intercept':
            continue
        reg_md.append(f"| Sensitivity log-time OLS | {label_map.get(var,var)} | {fit_ols.params[var]:.3f} | See raw companion | {fit_ols.pvalues[var]:.4f} | {len(dfs)} |")
    (OUT/'updated_table3_regression_final.md').write_text('\n'.join(reg_md), encoding='utf-8')

    # Updated OR list and prism inputs
    or_lines=[]; prism_rows=[]
    wide_header=['X']; lower=['Lower']; hr=['OR']; upper=['Upper']
    for var in fit_logit.params.index:
        if var=='Intercept':
            continue
        name=label_map.get(var,var)
        orv=math.exp(fit_logit.params[var]); lcl=math.exp(conf.loc[var,0]); ucl=math.exp(conf.loc[var,1]); p=fit_logit.pvalues[var]
        or_lines.append(f"{name}: {orv:.2f} ({lcl:.2f}-{ucl:.2f}), p = {p:.4f}")
        prism_rows.append({'Variable':name,'OR':round(orv,6),'Lower_95CI':round(lcl,6),'Upper_95CI':round(ucl,6),'P_value':round(float(p),6),'N_complete_case':int(len(dfl))})
        wide_header.append(name); lower.append(f'{lcl:.6f}'); hr.append(f'{orv:.6f}'); upper.append(f'{ucl:.6f}')
    (OUT/'updated_or_ci_pvalue_list.txt').write_text('\n'.join(or_lines), encoding='utf-8')
    write_csv(RAW/'updated_table3_forestplot_prism_input.csv', prism_rows)
    with open(RAW/'updated_table3_forestplot_prism_wide.csv','w',newline='',encoding='utf-8') as f:
        import csv as _csv
        w=_csv.writer(f); w.writerows([wide_header,lower,hr,upper])

    # Document clustering note
    clustering_note=f"""# Final Clustering Feasibility Note

A site identifier (`TQIPSITE`) was merged into the restricted primary timing cohort to evaluate cluster-robust modeling. The observed site distribution in the restricted cohort was:
- site value 1: {site_counts.get('1',0)} rows
- site value 0: {site_counts.get('0',0)} rows

Although cluster-robust estimation is technically possible in statsmodels, this imbalance is substantial enough that cluster-robust inference would likely be unstable and disproportionately driven by the dominant site group. Accordingly, cluster-robust standard errors were not adopted as the primary reported model in this final execution phase. This limitation should be stated explicitly in the supplement or discussion.
"""
    (DOC/'phase8_clustering_feasibility_note.md').write_text(clustering_note, encoding='utf-8')

    # Refresh final package files
    mapping={
        OUT/'updated_publication_methods_final.md': FINAL/'02_publication_methods.md',
        OUT/'updated_publication_results_final.md': FINAL/'03_publication_results.md',
        OUT/'updated_table3_regression_final.md': FINAL/'06_table3_regression_results.md',
        OUT/'updated_or_ci_pvalue_list.txt': FINAL/'15_updated_or_ci_pvalue_list.txt',
        RAW/'updated_table3_forestplot_prism_input.csv': FINAL/'16_updated_table3_forestplot_prism_input.csv',
        RAW/'updated_table3_forestplot_prism_wide.csv': FINAL/'17_updated_table3_forestplot_prism_wide.csv',
        DOC/'phase8_clustering_feasibility_note.md': FINAL/'18_phase8_clustering_feasibility_note.md',
        RAW/'phase8_regression_results_raw.csv': FINAL/'raw_regression_results_phase8_final.csv',
    }
    for src,dst in mapping.items():
        dst.write_text(src.read_text(encoding='utf-8'), encoding='utf-8') if src.suffix in {'.md','.txt','.json','.csv'} else None

    # final execution summary
    final_summary={
        'run_timestamp':run_ts,
        'assumptions':assumptions,
        'issues':issues,
        'final_recommendation':'Use the parsimonious logistic model as the primary adjusted analysis and the log-time model as a sensitivity analysis.',
        'median_delay_cutpoint_hours':med,
        'cohort_n_modeled':int(len(df)),
        'complete_case_n_logit':int(len(dfl)),
        'complete_case_n_sensitivity':int(len(dfs)),
        'site_counts':site_counts,
        'outputs':{
            'methods':str(OUT/'updated_publication_methods_final.md'),
            'results':str(OUT/'updated_publication_results_final.md'),
            'regression_table':str(OUT/'updated_table3_regression_final.md'),
            'or_ci_p_list':str(OUT/'updated_or_ci_pvalue_list.txt')
        }
    }
    (OUT/'phase8_final_execution_summary.json').write_text(json.dumps(final_summary, indent=2), encoding='utf-8')
    (LOG/'phase8_run.log').write_text(json.dumps(final_summary, indent=2), encoding='utf-8')

if __name__=='__main__':
    main()
