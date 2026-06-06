#!/usr/bin/env python3
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from datetime import datetime


#PATH MUST MATCH FILE LOCATION, THESE MUST BE EDITED IF ATTEMPTING TO REPLICATE
#Outputs set to Desktop at present 
BASE = Path('/Users/___/Desktop/PUF AY 2024/CSV')
OUT = Path('/Users/___/Desktop/tqip_ocular_study_phase1/outputs')
LOG = Path('/Users/___/Desktop/tqip_ocular_study_phase1/logs')
DOC = Path('/Users/___/Desktop/tqip_ocular_study_phase1/docs')

FILES = {
    'trauma': BASE / 'PUF_TRAUMA.csv',
    'icd_dx': BASE / 'PUF_ICDDIAGNOSIS.csv',
    'icd_dx_lookup': BASE / 'PUF_ICDDIAGNOSIS_LOOKUP.csv',
    'icd_px': BASE / 'PUF_ICDPROCEDURE.csv',
    'icd_px_lookup': BASE / 'PUF_ICDPROCEDURE_LOOKUP.csv',
    'ais': BASE / 'PUF_AISDIAGNOSIS.csv',
    'ais_lookup': BASE / 'PUF_AISDIAGNOSIS_LOOKUP.csv',
    'events': BASE / 'PUF_HOSPITALEVENTS.csv',
    'preexist': BASE / 'PUF_PREEXISTINGCONDITIONS.csv',
    'inclusion': BASE / 'TQP_INCLUSION.csv',
    'trauma_lookup': BASE / 'PUF_TRAUMA_LOOKUP.csv',
    'var_formats': BASE / 'PUF Variable Formats.csv',
}

RUN_TS = datetime.now().isoformat()

# Broad discovery terms for phase 1 only. These do NOT define the final cohort.
DISCOVERY_TERMS = [
    'eye','ocular','orbit','orbital','globe','eyelid','lacrimal','retina','cornea',
    'conjunct','sclera','optic','choroid','lens','vitre','canalicul','extraocular',
    'hyphema','enucleat','retrobulbar'
]

# Exclusion terms for broad lookup discovery lists to reduce obvious non-trauma/non-acute noise.
DISCOVERY_EXCLUDE_TERMS = [
    'congenital','family history','without abnormal findings','neoplasm','melanoma','carcinoma',
    'diabetic','glaucoma secondary to eye inflammation','retinopathy of prematurity',
    'hypertensive retinopathy','routine','exam','prematurity'
]

# Simple phase-1 injury strata hints. 
EMERGENT_HINT_TERMS = [
    'rupture','avulsion','enucleation','optic nerve','intraocular foreign body','laceration',
    'open','globe','retina','cornea','sclera','choroid','hyphema','retrobulbar'
]
ORBITAL_ADNEXAL_HINT_TERMS = [
    'orbit','orbital','eyelid','lacrimal','canalicul','adnexa','extraocular muscle'
]

# Procedure-level major competing intervention discovery terms for phase 1 descriptive work.
MCI_TERMS = {
    'laparotomy': ['laparotomy'],
    'thoracotomy': ['thoracotomy'],
    'sternotomy': ['sternotomy'],
    'angiography_embolization_stenting': ['embolization', 'stenting', 'angiogram'],
    'pelvic_packing': ['extraperitoneal pelvic packing', 'pelvic packing'],
    'neurosurgery_hint': ['craniotomy', 'craniectomy', 'ventriculostomy', 'intracranial', 'spinal fusion', 'spinal decompression'],
    'orthopedic_fixation_hint': ['reposition with internal fixation', 'insertion of internal fixation', 'external fixation']
}


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


def write_txt(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)


def row_count(path):
    with open(path, 'r', encoding='utf-8-sig', newline='') as f:
        next(f)
        return sum(1 for _ in f)


def read_header(path):
    with open(path, 'r', encoding='utf-8-sig', newline='') as f:
        reader = csv.reader(f)
        return next(reader)


def contains_any(text, terms):
    t = (text or '').lower()
    return any(term in t for term in terms)


def contains_excluded(text, terms):
    t = (text or '').lower()
    return any(term in t for term in terms)


def classify_hint(text):
    t = (text or '').lower()
    emergent = any(term in t for term in EMERGENT_HINT_TERMS)
    orbital = any(term in t for term in ORBITAL_ADNEXAL_HINT_TERMS)
    if emergent and orbital:
        return 'mixed_hint'
    if emergent:
        return 'emergent_hint'
    if orbital:
        return 'orbital_adnexal_hint'
    return 'unclassified_hint'


def build_lookup_candidates(path, code_field, desc_field, extra_filters=None):
    rows = []
    with open(path, 'r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            desc = row.get(desc_field, '')
            if contains_any(desc, DISCOVERY_TERMS) and not contains_excluded(desc, DISCOVERY_EXCLUDE_TERMS):
                if extra_filters and not extra_filters(row):
                    continue
                rows.append({
                    'code': row.get(code_field),
                    'description': desc,
                    'hint_group': classify_hint(desc)
                })
    return rows


def load_set_from_candidates(rows):
    return {r['code'] for r in rows if r.get('code')}


def summarize_candidate_rows(rows):
    by_hint = Counter(r['hint_group'] for r in rows)
    return {
        'n_candidates': len(rows),
        'hint_group_counts': dict(by_hint)
    }


def get_trauma_lookup_map():
    fmt_map = defaultdict(dict)
    with open(FILES['trauma_lookup'], 'r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            fmt_map[row['FmtName']][row['Start']] = row['Label']
    return fmt_map


def count_unique_keys(path, key_name):
    s = set()
    with open(path, 'r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            s.add(row[key_name])
    return len(s)


def phase1():
    issues = []
    summary = {
        'run_timestamp': RUN_TS,
        'base_dir': str(BASE),
        'workspace': str(OUT.parent),
        'files': {},
        'assumptions': [
            'Phase 1 uses broad lookup-driven discovery lists for candidate ocular/orbital diagnoses and procedures.',
            'Phase 1 outputs do not define the final analytic cohort.',
            'Timing variables with invalid BIU flags will be excluded from timing analyses in later phases.',
            'Observed time fields in this dataset appear to store decimal hours rather than whole-hour integers; Phase 1 parses hour fields as floats.',
        ],
        'issues': issues,
    }

    # File inventory
    for name, path in FILES.items():
        try:
            summary['files'][name] = {
                'path': str(path),
                'exists': path.exists(),
                'header': read_header(path),
                'row_count_excluding_header': row_count(path)
            }
        except Exception as e:
            issues.append(f'File inventory error for {name}: {e}')
            summary['files'][name] = {
                'path': str(path),
                'exists': path.exists(),
                'error': str(e)
            }

    # Candidate code discovery from lookups
    dx_candidates = build_lookup_candidates(FILES['icd_dx_lookup'], 'ICDDIAGNOSISCODE', 'ICDDiagnosisCode_Desc')
    px_candidates = build_lookup_candidates(FILES['icd_px_lookup'], 'ICDPROCEDURECODE', 'ICDProcedureCode_Desc')
    ais_candidates = build_lookup_candidates(FILES['ais_lookup'], 'AISPREDOT', 'AISDESCRIPTION')

    # Save candidate lists
    write_json(OUT / 'phase1_dx_candidates.json', dx_candidates)
    write_json(OUT / 'phase1_px_candidates.json', px_candidates)
    write_json(OUT / 'phase1_ais_candidates.json', ais_candidates)

    summary['candidate_discovery'] = {
        'diagnosis_lookup': summarize_candidate_rows(dx_candidates),
        'procedure_lookup': summarize_candidate_rows(px_candidates),
        'ais_lookup': summarize_candidate_rows(ais_candidates),
    }

    dx_set = load_set_from_candidates(dx_candidates)
    px_set = load_set_from_candidates(px_candidates)
    ais_set = load_set_from_candidates(ais_candidates)

    # Build first-pass encounter sets
    dx_encounters = set()
    dx_code_counter = Counter()
    with open(FILES['icd_dx'], 'r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            code = row['ICDDIAGNOSISCODE']
            if code in dx_set:
                dx_encounters.add(row['Inc_Key'])
                dx_code_counter[code] += 1

    px_encounters = set()
    px_code_counter = Counter()
    px_first_time = {}
    invalid_px_timing = 0
    with open(FILES['icd_px'], 'r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            code = row['ICDPROCEDURECODE']
            if code in px_set:
                key = row['Inc_Key']
                px_encounters.add(key)
                px_code_counter[code] += 1
                biu = row.get('HOSPITALPROCEDURESTARTDH_BIU', '')
                try:
                    day = int(float(row['HOSPITALPROCEDURESTARTDAYS'])) if row['HOSPITALPROCEDURESTARTDAYS'] != '' else None
                    hr = float(row['HOSPITALPROCEDURESTARTHRS']) if row['HOSPITALPROCEDURESTARTHRS'] != '' else None
                except ValueError:
                    day, hr = None, None
                if biu not in ('', '0', '1') and (day is None or hr is None):
                    invalid_px_timing += 1
                if day is not None and hr is not None:
                    stamp = day * 24 + hr
                    if key not in px_first_time or stamp < px_first_time[key]:
                        px_first_time[key] = stamp

    ais_encounters = set()
    ais_code_counter = Counter()
    with open(FILES['ais'], 'r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            code = row['AISPreDot']
            if code in ais_set:
                ais_encounters.add(row['inc_key'])
                ais_code_counter[code] += 1

    # Trauma table pass for severe trauma and timing QC
    direct_arrival_keys = set()
    transfer_keys = set()
    severe_iss16_keys = set()
    valid_arrival_timing_keys = set()
    invalid_arrival_timing_keys = set()
    death_keys = set()
    survivor_keys = set()
    total_trauma_rows = 0
    timing_negative_count = 0
    timing_zero_count = 0
    timing_positive_count = 0
    elapsed_hours_values = []

    trauma_fields_of_interest = {
        'sex': Counter(),
        'ethnicity': Counter(),
        'payer': Counter(),
        'ed_disp': Counter(),
        'hosp_disp': Counter(),
        'highest_activation': Counter(),
        'hmrrhg_type': Counter(),
        'angiography': Counter(),
    }

    with open(FILES['trauma'], 'r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            total_trauma_rows += 1
            key = row['inc_key']

            # direct/transfer
            if row.get('INTERFACILITYTRANSFER') == '1':
                transfer_keys.add(key)
            elif row.get('INTERFACILITYTRANSFER') == '2':
                direct_arrival_keys.add(key)

            # severe trauma by ISS>=16 first pass only
            try:
                iss = float(row['ISS']) if row['ISS'] != '' else None
            except ValueError:
                iss = None
            if iss is not None and iss >= 16:
                severe_iss16_keys.add(key)

            # arrival timing QC
            arrival_biu = row.get('HOSPITALARRIVALDH_BIU', '')
            try:
                ad = int(float(row['HOSPITALARRIVALDAYS'])) if row['HOSPITALARRIVALDAYS'] != '' else None
                ah = float(row['HOSPITALARRIVALHRS']) if row['HOSPITALARRIVALHRS'] != '' else None
            except ValueError:
                ad, ah = None, None
            if ad is not None and ah is not None:
                valid_arrival_timing_keys.add(key)
            else:
                invalid_arrival_timing_keys.add(key)

            # dispositions
            if row.get('HOSPDISCHARGEDISPOSITION') == '5':
                death_keys.add(key)
            else:
                survivor_keys.add(key)

            # coded fields for descriptive QC
            trauma_fields_of_interest['sex'][row.get('SEX', '')] += 1
            trauma_fields_of_interest['ethnicity'][row.get('ETHNICITY', '')] += 1
            trauma_fields_of_interest['payer'][row.get('PRIMARYMETHODPAYMENT', '')] += 1
            trauma_fields_of_interest['ed_disp'][row.get('EDDISCHARGEDISPOSITION', '')] += 1
            trauma_fields_of_interest['hosp_disp'][row.get('HOSPDISCHARGEDISPOSITION', '')] += 1
            trauma_fields_of_interest['highest_activation'][row.get('HIGHESTACTIVATION', '')] += 1
            trauma_fields_of_interest['hmrrhg_type'][row.get('HMRRHGCTRLSURGTYPE', '')] += 1
            trauma_fields_of_interest['angiography'][row.get('ANGIOGRAPHY', '')] += 1

            # elapsed timing for ocular procedure candidates if available
            if key in px_first_time and ad is not None and ah is not None:
                arrival_stamp = ad * 24 + ah
                elapsed = px_first_time[key] - arrival_stamp
                elapsed_hours_values.append(elapsed)
                if elapsed < 0:
                    timing_negative_count += 1
                elif elapsed == 0:
                    timing_zero_count += 1
                else:
                    timing_positive_count += 1

    trauma_lookup_map = get_trauma_lookup_map()

    # First-pass broad cohort sets
    any_ocular_candidate = dx_encounters | px_encounters | ais_encounters
    dx_and_or_ais = dx_encounters | ais_encounters
    broad_operable_candidate = any_ocular_candidate & px_encounters
    severe_broad_candidate = any_ocular_candidate & severe_iss16_keys
    severe_operable_candidate = severe_broad_candidate & px_encounters
    direct_severe_operable_candidate = severe_operable_candidate & direct_arrival_keys
    transfer_severe_operable_candidate = severe_operable_candidate & transfer_keys
    valid_timing_direct_severe_operable = direct_severe_operable_candidate & valid_arrival_timing_keys & set(px_first_time.keys())

    # Top codes tables
    dx_lookup_desc = {}
    with open(FILES['icd_dx_lookup'], 'r', encoding='utf-8-sig', newline='') as f:
        for row in csv.DictReader(f):
            dx_lookup_desc[row['ICDDIAGNOSISCODE']] = row['ICDDiagnosisCode_Desc']

    px_lookup_desc = {}
    with open(FILES['icd_px_lookup'], 'r', encoding='utf-8-sig', newline='') as f:
        for row in csv.DictReader(f):
            px_lookup_desc[row['ICDPROCEDURECODE']] = row['ICDProcedureCode_Desc']

    ais_lookup_desc = {}
    with open(FILES['ais_lookup'], 'r', encoding='utf-8-sig', newline='') as f:
        for row in csv.DictReader(f):
            ais_lookup_desc[row['AISPREDOT']] = row['AISDESCRIPTION']

    top_dx = [{'code': c, 'n': n, 'description': dx_lookup_desc.get(c, '')} for c, n in dx_code_counter.most_common(50)]
    top_px = [{'code': c, 'n': n, 'description': px_lookup_desc.get(c, '')} for c, n in px_code_counter.most_common(50)]
    top_ais = [{'code': c, 'n': n, 'description': ais_lookup_desc.get(c, '')} for c, n in ais_code_counter.most_common(50)]

    write_json(OUT / 'phase1_top_dx_codes.json', top_dx)
    write_json(OUT / 'phase1_top_px_codes.json', top_px)
    write_json(OUT / 'phase1_top_ais_codes.json', top_ais)

    # Decode selected trauma file distributions
    selected_formats = {
        'sex': 'Sex',
        'ethnicity': 'Ethnicity',
        'payer': 'PrimaryMethodPayment',
        'ed_disp': 'EdDischargeDisposition',
        'hosp_disp': 'HospDischargeDisposition',
        'hmrrhg_type': 'HmrrhgCtrlSurgType',
        'angiography': 'Angiography',
    }
    decoded_distributions = {}
    for key, fmt in selected_formats.items():
        mapping = trauma_lookup_map.get(fmt, {})
        decoded_distributions[key] = [
            {'code': code, 'label': mapping.get(code, 'UNKNOWN/UNMAPPED'), 'n': n}
            for code, n in trauma_fields_of_interest[key].most_common()
        ]

    # First-pass issue logging
    if len(dx_candidates) == 0:
        issues.append('No diagnosis candidates were identified from lookup discovery terms.')
    if len(px_candidates) == 0:
        issues.append('No procedure candidates were identified from lookup discovery terms.')
    if timing_negative_count > 0:
        issues.append(f'Negative elapsed-hour values found for {timing_negative_count} candidate operative encounters.')
    if len(transfer_severe_operable_candidate) > 0:
        issues.append('Transfer patients are present in the severe operative candidate cohort - should be /remain excluded.')
    issues.append('Major issue encountered and corrected during Phase 1: hospital/procedure hour fields are stored as decimal hours. (Oh no.)')

    # Summary tables
    summary['phase1_counts'] = {
        'total_trauma_encounters': total_trauma_rows,
        'unique_trauma_encounters': count_unique_keys(FILES['trauma'], 'inc_key'),
        'broad_dx_candidate_encounters': len(dx_encounters),
        'broad_px_candidate_encounters': len(px_encounters),
        'broad_ais_candidate_encounters': len(ais_encounters),
        'any_ocular_candidate_encounters_union': len(any_ocular_candidate),
        'broad_diagnosis_or_ais_candidate_encounters': len(dx_and_or_ais),
        'broad_operable_candidate_encounters': len(broad_operable_candidate),
        'severe_iss16_candidate_encounters': len(severe_iss16_keys),
        'severe_broad_candidate_encounters': len(severe_broad_candidate),
        'severe_operable_candidate_encounters': len(severe_operable_candidate),
        'direct_severe_operable_candidate_encounters': len(direct_severe_operable_candidate),
        'transfer_severe_operable_candidate_encounters': len(transfer_severe_operable_candidate),
        'direct_severe_operable_with_valid_arrival_and_px_time': len(valid_timing_direct_severe_operable),
    }

    summary['timing_qc'] = {
        'candidate_encounters_with_first_px_time': len(px_first_time),
        'valid_arrival_timing_encounters': len(valid_arrival_timing_keys),
        'invalid_arrival_timing_encounters': len(invalid_arrival_timing_keys),
        'invalid_px_timing_rows_among_candidate_px_rows': invalid_px_timing,
        'elapsed_hours_negative_count': timing_negative_count,
        'elapsed_hours_zero_count': timing_zero_count,
        'elapsed_hours_positive_count': timing_positive_count,
        'elapsed_hours_summary_if_any': {
            'n': len(elapsed_hours_values),
            'min': min(elapsed_hours_values) if elapsed_hours_values else None,
            'median_approx_sorted': sorted(elapsed_hours_values)[len(elapsed_hours_values)//2] if elapsed_hours_values else None,
            'max': max(elapsed_hours_values) if elapsed_hours_values else None,
        }
    }

    summary['descriptive_distributions'] = decoded_distributions
    summary['top_codes'] = {
        'diagnosis': top_dx,
        'procedure': top_px,
        'ais': top_ais,
    }

    # Save full-readable summary
    write_json(OUT / 'phase1_summary.json', summary)

    # Save human readable report
    report_lines = []
    report_lines.append('PHASE 1 DESCRIPTIVE BUILD REPORT')
    report_lines.append(f'Run timestamp: {RUN_TS}')
    report_lines.append('')
    report_lines.append('Scope note: Phase 1 uses broad lookup-driven discovery lists for candidate ocular/orbital diagnoses and procedures.')
    report_lines.append('')
    report_lines.append('FILE INVENTORY')
    for name, meta in summary['files'].items():
        report_lines.append(f"- {name}: rows={meta.get('row_count_excluding_header')} path={meta.get('path')}")
    report_lines.append('')
    report_lines.append('FIRST-PASS CANDIDATE DISCOVERY COUNTS')
    for k, v in summary['candidate_discovery'].items():
        report_lines.append(f"- {k}: {v['n_candidates']} candidates; hints={v['hint_group_counts']}")
    report_lines.append('')
    report_lines.append('PHASE 1 COHORT COUNTS')
    for k, v in summary['phase1_counts'].items():
        report_lines.append(f'- {k}: {v}')
    report_lines.append('')
    report_lines.append('TIMING QC')
    for k, v in summary['timing_qc'].items():
        report_lines.append(f'- {k}: {v}')
    report_lines.append('')
    report_lines.append('MAJOR ISSUES / NOTES')
    if issues:
        for issue in issues:
            report_lines.append(f'- {issue}')
    else:
        report_lines.append('- No major issues recorded in Phase 1.')
    report_lines.append('')
    report_lines.append('IMPORTANT INTERPRETIVE NOTE')
    report_lines.append('- Broad lookup discovery remains intentionally overinclusive.')
    write_txt(OUT / 'phase1_report.txt', '\n'.join(report_lines) + '\n')

    # Save run log
    write_txt(LOG / 'phase1_run.log', '\n'.join(report_lines) + '\n')

    # Save assumptions doc
    assumptions = [
        'All analysis in Phase 1 was performed from raw CSV files in /Users/___/Desktop/PUF AY 2024/CSV.',
        'Encounter linkage assumes inc_key/Inc_Key refers to the same trauma encounter across files.',
        'ISS>=16 is used in Phase 1 as a descriptive severe-trauma screen only and not as the finalized severe polytrauma definition.',
    ]
    write_txt(DOC / 'phase1_assumptions.txt', '\n'.join(f'- {a}' for a in assumptions) + '\n')


if __name__ == '__main__':
    phase1()
