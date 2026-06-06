#!/usr/bin/env python3
import csv, json, math
from pathlib import Path
from collections import Counter
from datetime import datetime

BASE = Path('/Users/___/Desktop/PUF AY 2024/CSV')
PHASE3 = Path('/Users/___/Desktop/tqip_ocular_study_phase3/outputs')
WORK = Path('/Users/___/Desktop/tqip_ocular_study_phase7')
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
    assumptions = []
    issues = []

    primary = load_csv(PHASE3 / 'phase3_primary_timing_dataset.csv')
    negative = load_csv(PHASE3 / 'phase3_negative_timing_review.csv')


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
        issues.append(f'{missing_site} primary timing rows were missing TQIPSITE after merge.')
    if not cluster_ready:
        issues.append('Site-level clustering may not yet be fully ready; verify TQIPSITE completeness before final cluster-robust analysis.')

   
    neg_appendix = f"""# Negative Timing Data Integrity Appendix Text

A total of {total_neg} encounters in the locked operable dataset demonstrated negative elapsed time from hospital arrival to first qualifying ocular/orbital procedure and were excluded from the primary timing analysis. 

Using rule-based categorization of the excluded records, the anomalies were grouped as follows:
"""
    for row in neg_summary_rows:
        neg_appendix += f"\n- **{row['category']}**: {row['n']} records ({row['pct']:.1f}%)"
    neg_appendix += """

    clustering_text = """

if __name__ == '__main__':
    main()
