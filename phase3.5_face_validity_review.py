#!/usr/bin/env python3
import csv, json
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime

PHASE3 = Path('/Users/Zaid/Desktop/tqip_ocular_study_phase3/outputs')
WORK = Path('/Users/Zaid/Desktop/tqip_ocular_study_phase35')
OUT = WORK / 'outputs'
LOG = WORK / 'logs'
DOC = WORK / 'docs'


def load_csv(path):
    with open(path, newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def main():
    run_ts = datetime.now().isoformat()
    issues = []
    assumptions = [
        'Phase 3.5 is a face-validity and readiness review, not a modeling phase.',
        'Primary goals are to inspect negative timing cases, first-procedure code plausibility, and stratum balance.',
        'Recommendation will be based on safety and methodological defensibility rather than maximizing sample size.',
    ]

    summary = json.loads((PHASE3 / 'phase3_summary.json').read_text())
    codebook = json.loads((PHASE3 / 'phase3_locked_codebook.json').read_text())
    locked = load_csv(PHASE3 / 'phase3_locked_operable_dataset.csv')
    primary = load_csv(PHASE3 / 'phase3_primary_timing_dataset.csv')
    neg = load_csv(PHASE3 / 'phase3_negative_timing_review.csv') if (PHASE3 / 'phase3_negative_timing_review.csv').exists() else []

    # Review top first-procedure codes in primary timing dataset
    px_counts = Counter(r['first_px_code'] for r in primary if r['first_px_code'])
    stratum_by_px = defaultdict(Counter)
    elapsed_by_stratum = defaultdict(list)
    for r in primary:
        code = r['first_px_code']
        stratum = r['stratum']
        if code:
            stratum_by_px[code][stratum] += 1
        try:
            if r['elapsed_hours_to_first_px'] not in ('', None):
                elapsed_by_stratum[stratum].append(float(r['elapsed_hours_to_first_px']))
        except ValueError:
            pass

    top_px_review = []
    for code, n in px_counts.most_common(25):
        top_px_review.append({
            'code': code,
            'n': n,
            'stratum_mix': dict(stratum_by_px[code])
        })

    # Negative timing review
    neg_px_counts = Counter(r['first_px_code'] for r in neg if r['first_px_code'])
    neg_stratum_counts = Counter(r['stratum'] for r in neg)
    neg_transfer_counts = Counter(r['transfer_group'] for r in neg)
    neg_summary = {
        'n_negative_rows': len(neg),
        'top_first_px_codes': neg_px_counts.most_common(20),
        'stratum_counts': dict(neg_stratum_counts),
        'transfer_counts': dict(neg_transfer_counts),
    }

    # Locked dataset face-validity checks
    locked_strata = Counter(r['stratum'] for r in locked)
    primary_strata = Counter(r['stratum'] for r in primary)
    mortality_by_stratum = Counter()
    major_comp_by_stratum = Counter()
    denom_by_stratum = Counter()
    for r in locked:
        s = r['stratum']
        denom_by_stratum[s] += 1
        if r['in_hospital_mortality'] == '1':
            mortality_by_stratum[s] += 1
        if r['major_systemic_complication'] == '1':
            major_comp_by_stratum[s] += 1

    stratum_metrics = []
    for s, d in denom_by_stratum.items():
        stratum_metrics.append({
            'stratum': s,
            'n_locked': d,
            'n_primary_timing': primary_strata.get(s, 0),
            'mortality_n': mortality_by_stratum.get(s, 0),
            'major_complication_n': major_comp_by_stratum.get(s, 0),
        })

    # Compute simple medians by stratum
    elapsed_stats = {}
    for s, vals in elapsed_by_stratum.items():
        vals = sorted(vals)
        elapsed_stats[s] = {
            'n': len(vals),
            'median_hours': vals[len(vals)//2] if vals else None,
            'min_hours': vals[0] if vals else None,
            'max_hours': vals[-1] if vals else None,
        }

    # Decision logic
    emergent_n = locked_strata.get('emergent_ocular', 0)
    orbital_n = locked_strata.get('orbital_adnexal', 0)
    mixed_n = locked_strata.get('mixed_emergent_priority', 0)
    neg_n = len(neg)
    primary_n = len(primary)

    if emergent_n < 30:
        issues.append('The emergent ocular operative stratum is very small, limiting stable stratum-specific modeling and suggesting either true rarity or an overly restrictive emergent codebook.')
    if orbital_n > 0 and emergent_n > 0 and orbital_n / max(emergent_n,1) > 20:
        issues.append('The final cohort is heavily dominated by orbital/adnexal cases relative to emergent ocular cases, reinforcing the need for separate reporting and possibly limiting emergent-focused inference.')
    if neg_n > 0:
        issues.append('Negative elapsed-time cases remain present after locking; exclusion from the primary timing dataset was appropriate and should be retained.')
    if primary_n < 1000:
        issues.append('Primary timing cohort size is modest after all restrictions, which may limit multivariable complexity.')

    # Determine recommendation
    # safest route: proceed only for orbital/adnexal-led primary timing analyses, keep emergent as descriptive/sensitivity unless refined.
    if emergent_n < 30:
        recommendation = 'proceed_with_restriction'
        recommendation_text = (
            'Proceed to modeling only for the primary direct-arrival timing analysis with orbital/adnexal-dominant or pooled-but-stratified reporting, '
            'while treating emergent ocular cases as descriptive or sensitivity-only unless the codebook is deliberately broadened after review.'
        )
    else:
        recommendation = 'proceed'
        recommendation_text = 'Proceed to modeling with locked cohort and planned stratification.'

    out = {
        'run_timestamp': run_ts,
        'assumptions': assumptions,
        'issues': issues,
        'summary_counts': summary.get('dataset_counts', {}),
        'locked_strata': dict(locked_strata),
        'primary_strata': dict(primary_strata),
        'stratum_metrics': stratum_metrics,
        'elapsed_stats_by_stratum': elapsed_stats,
        'top_first_px_codes_primary': top_px_review,
        'negative_timing_review': neg_summary,
        'recommendation': recommendation,
        'recommendation_text': recommendation_text,
    }

    (OUT / 'phase35_face_validity_summary.json').write_text(json.dumps(out, indent=2), encoding='utf-8')
    with open(OUT / 'phase35_face_validity_report.txt', 'w', encoding='utf-8') as f:
        f.write('PHASE 3.5 FACE-VALIDITY REVIEW REPORT\n')
        f.write(f'Run timestamp: {run_ts}\n\n')
        f.write('This review examined the locked Phase 3 outputs before modeling, focusing on negative timing cases, first-procedure face validity, and cohort balance.\n\n')
        f.write('LOCKED STRATA\n')
        for k,v in locked_strata.items():
            f.write(f'- {k}: {v}\n')
        f.write('\nPRIMARY TIMING STRATA\n')
        for k,v in primary_strata.items():
            f.write(f'- {k}: {v}\n')
        f.write('\nELAPSED TIME BY STRATUM\n')
        for k,v in elapsed_stats.items():
            f.write(f'- {k}: {v}\n')
        f.write('\nNEGATIVE TIMING REVIEW\n')
        f.write(f"- negative rows: {neg_summary['n_negative_rows']}\n")
        f.write(f"- negative stratum counts: {neg_summary['stratum_counts']}\n")
        f.write(f"- negative transfer counts: {neg_summary['transfer_counts']}\n")
        f.write('\nTOP FIRST-PROCEDURE CODES IN PRIMARY TIMING DATASET\n')
        for row in top_px_review[:20]:
            f.write(f"- {row['code']}: n={row['n']} stratum_mix={row['stratum_mix']}\n")
        f.write('\nMAJOR ISSUES / NOTES\n')
        if issues:
            for item in issues:
                f.write(f'- {item}\n')
        else:
            f.write('- No major face-validity concerns identified.\n')
        f.write('\nRECOMMENDATION\n')
        f.write(f'- {recommendation}: {recommendation_text}\n')

    (DOC / 'phase35_recommendation.txt').write_text(recommendation_text + '\n\n' + '\n'.join(issues), encoding='utf-8')
    (LOG / 'phase35_run.log').write_text(json.dumps({'run_timestamp': run_ts, 'issues': issues, 'recommendation': recommendation}, indent=2), encoding='utf-8')

if __name__ == '__main__':
    main()
