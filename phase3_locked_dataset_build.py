#!/usr/bin/env python3
import csv, json, math, re
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime

BASE = Path('/Users/Zaid/Desktop/PUF AY 2024/CSV')
PHASE2 = Path('/Users/Zaid/Desktop/tqip_ocular_study_phase2/outputs')
WORK = Path('/Users/Zaid/Desktop/tqip_ocular_study_phase3')
OUT = WORK / 'outputs'
LOG = WORK / 'logs'
DOC = WORK / 'docs'

FILES = {
    'trauma': BASE / 'PUF_TRAUMA.csv',
    'icd_dx': BASE / 'PUF_ICDDIAGNOSIS.csv',
    'icd_px': BASE / 'PUF_ICDPROCEDURE.csv',
    'ais': BASE / 'PUF_AISDIAGNOSIS.csv',
    'events': BASE / 'PUF_HOSPITALEVENTS.csv',
    'preexist': BASE / 'PUF_PREEXISTINGCONDITIONS.csv',
    'inclusion': BASE / 'TQP_INCLUSION.csv',
}

# Approved clinical decisions translated into reproducible rule-based lists.
EMERGENT_DX_TERMS = [
    'open wound of eyeball', 'injury of optic nerve', 'rupture of eye', 'laceration of eye',
    'penetrating wound', 'perforating wound', 'retained intraocular foreign body', 'hyphema',
    'injury of conjunctiva and corneal abrasion without foreign body', 'injury of conjunctiva and corneal abrasion with foreign body',
    'injury of globe', 'traumatic enucleation', 'avulsion of eye', 'retrobulbar', 'orbital compartment syndrome'
]
ORBITAL_DX_TERMS = [
    'fracture of orbital floor', 'fracture of orbit', 'fracture of medial orbital wall',
    'fracture of lateral orbital wall', 'fracture of orbital roof', 'eyelid and periocular area',
    'lacrimal', 'canalicul', 'orbital blowout'
]
DX_EXCLUDE_TERMS = [
    'superficial', 'contusion of eyelid', 'abrasion', 'minor', 'without foreign body of eyelid',
    'burn', 'thermal', 'chemical', 'subsequent encounter', 'sequela', 'history of', 'chronic',
    'congenital', 'neoplasm', 'examination', 'glaucoma', 'cataract', 'retinopathy', 'conjunctivitis',
    'blepharitis', 'degeneration', 'atrophy', 'sicca', 'dry eye'
]

EMERGENT_PX_TERMS = [
    'repair right eye', 'repair left eye', 'repair optic nerve', 'repair right sclera', 'repair left sclera',
    'repair right cornea', 'repair left cornea', 'repair right retina', 'repair left retina',
    'drainage of right orbit', 'drainage of left orbit', 'drainage of right eye', 'drainage of left eye',
    'extirpation of matter from right eye', 'extirpation of matter from left eye', 'vitreous', 'canthotomy', 'cantholysis'
]
ORBITAL_PX_TERMS = [
    'reposition right orbit', 'reposition left orbit', 'repair right upper eyelid', 'repair left upper eyelid',
    'repair right lower eyelid', 'repair left lower eyelid', 'repair right lacrimal duct', 'repair left lacrimal duct',
    'insertion of internal fixation device into right orbit', 'insertion of internal fixation device into left orbit',
    'repair right orbit', 'repair left orbit', 'reposition right lacrimal bone', 'reposition left lacrimal bone'
]
PX_EXCLUDE_TERMS = [
    'inspection', 'computerized tomography', 'plain radiography', 'magnetic resonance imaging',
    'ultrasonography', 'diagnostic', 'introduction of', 'revision of', 'removal of device', 'prosthetic'
]

SYSTEMIC_COMPLICATIONS = {
    '4',  # AKI
    '5',  # ARDS
    '8',  # Cardiac arrest with CPR
    '14', # DVT
    '18', # MI
    '20', # Pneumonia
    '21', # PE
    '22', # Stroke/CVA
    '32', # Severe sepsis
    '35', # VAP
}


def normalize(s):
    return re.sub(r'\s+', ' ', (s or '').strip().lower())


def load_review_tables():
    dx_review = []
    with open(PHASE2 / 'phase2_dx_review_table.csv', newline='', encoding='utf-8') as f:
        dx_review = list(csv.DictReader(f))
    px_review = []
    with open(PHASE2 / 'phase2_px_review_table.csv', newline='', encoding='utf-8') as f:
        px_review = list(csv.DictReader(f))
    ais_review = []
    with open(PHASE2 / 'phase2_ais_review_table.csv', newline='', encoding='utf-8') as f:
        ais_review = list(csv.DictReader(f))
    return dx_review, px_review, ais_review


def build_locked_code_lists(dx_review, px_review, ais_review):
    emergent_dx = set()
    orbital_dx = set()
    excluded_dx = set()
    for row in dx_review:
        desc = normalize(row['description'])
        code = row['code']
        if any(t in desc for t in DX_EXCLUDE_TERMS):
            excluded_dx.add(code)
            continue
        if any(t in desc for t in EMERGENT_DX_TERMS):
            emergent_dx.add(code)
        elif any(t in desc for t in ORBITAL_DX_TERMS):
            orbital_dx.add(code)

    emergent_px = set()
    orbital_px = set()
    all_locked_px = set()
    for row in px_review:
        desc = normalize(row['description'])
        code = row['code']
        if any(t in desc for t in PX_EXCLUDE_TERMS):
            continue
        if any(t in desc for t in EMERGENT_PX_TERMS):
            emergent_px.add(code)
            all_locked_px.add(code)
        elif any(t in desc for t in ORBITAL_PX_TERMS):
            orbital_px.add(code)
            all_locked_px.add(code)

    ais_support = set()
    for row in ais_review:
        desc = normalize(row['description'])
        code = row['code']
        if row['triage_label'] != 'candidate_include_review':
            continue
        if 'minor; superficial' in desc or 'abrasion' in desc or 'contusion; hematoma' in desc:
            continue
        ais_support.add(code)

    return {
        'emergent_dx': emergent_dx,
        'orbital_dx': orbital_dx,
        'excluded_dx': excluded_dx,
        'emergent_px': emergent_px,
        'orbital_px': orbital_px,
        'all_locked_px': all_locked_px,
        'ais_support': ais_support,
    }


def load_trauma_core():
    trauma = {}
    with open(FILES['trauma'], newline='', encoding='utf-8-sig') as f:
        r = csv.DictReader(f)
        for row in r:
            enc = row['inc_key'].strip()
            try:
                iss = int(float(row['ISS'])) if row['ISS'] != '' else None
            except ValueError:
                iss = None
            try:
                ad = int(float(row['HOSPITALARRIVALDAYS'])) if row['HOSPITALARRIVALDAYS'] != '' else None
                ah = float(row['HOSPITALARRIVALHRS']) if row['HOSPITALARRIVALHRS'] != '' else None
            except ValueError:
                ad, ah = None, None
            trauma[enc] = {
                'iss': iss,
                'transfer': row['INTERFACILITYTRANSFER'].strip(),
                'arrival_day': ad,
                'arrival_hr': ah,
                'age': row['AgeYears'].strip(),
                'sex': row['SEX'].strip(),
                'ethnicity': row['ETHNICITY'].strip(),
                'payer': row['PRIMARYMETHODPAYMENT'].strip(),
                'sbp': row['SBP'].strip(),
                'pulse': row['PULSERATE'].strip(),
                'rr': row['RESPIRATORYRATE'].strip(),
                'temp': row['TEMPERATURE'].strip(),
                'spo2': row['PULSEOXIMETRY'].strip(),
                'gcsmotor': row['GCSMOTOR'].strip(),
                'totalgcs': row['TOTALGCS'].strip(),
                'eddisp': row['EDDISCHARGEDISPOSITION'].strip(),
                'hospdisp': row['HOSPDISCHARGEDISPOSITION'].strip(),
                'iculos': row['TOTALICULOS'].strip(),
                'ventdays': row['TOTALVENTDAYS'].strip(),
                'inpatientdays': row['INPATIENTDAYS'].strip(),
                'highestactivation': row['HIGHESTACTIVATION'].strip(),
                'prehosp_arrest': row['PREHOSPITALCARDIACARREST'].strip(),
                'hmrrhgtype': row['HMRRHGCTRLSURGTYPE'].strip(),
                'angiography': row['ANGIOGRAPHY'].strip(),
            }
    return trauma


def build_dx_flags(code_lists):
    dx_flags = defaultdict(lambda: {'emergent_dx': 0, 'orbital_dx': 0, 'codes': set()})
    with open(FILES['icd_dx'], newline='', encoding='utf-8-sig') as f:
        r = csv.DictReader(f)
        for row in r:
            enc = row['Inc_Key'].strip()
            code = row['ICDDIAGNOSISCODE'].strip()
            if code in code_lists['excluded_dx']:
                continue
            if code in code_lists['emergent_dx']:
                dx_flags[enc]['emergent_dx'] = 1
                dx_flags[enc]['codes'].add(code)
            elif code in code_lists['orbital_dx']:
                dx_flags[enc]['orbital_dx'] = 1
                dx_flags[enc]['codes'].add(code)
    return dx_flags


def build_ais_flags(code_lists):
    ais_flags = defaultdict(lambda: {'ais_support': 0, 'codes': set()})
    with open(FILES['ais'], newline='', encoding='utf-8-sig') as f:
        r = csv.DictReader(f)
        for row in r:
            enc = row['inc_key'].strip()
            code = row['AISPreDot'].strip()
            if code in code_lists['ais_support']:
                ais_flags[enc]['ais_support'] = 1
                ais_flags[enc]['codes'].add(code)
    return ais_flags


def build_px_flags_and_timing(code_lists):
    px_flags = defaultdict(lambda: {
        'emergent_px': 0, 'orbital_px': 0, 'first_px_day': None, 'first_px_hr': None, 'first_px_code': None,
        'codes': set()
    })
    for code_set_key, flag_key in [('emergent_px', 'emergent_px'), ('orbital_px', 'orbital_px')]:
        pass
    with open(FILES['icd_px'], newline='', encoding='utf-8-sig') as f:
        r = csv.DictReader(f)
        for row in r:
            enc = row['Inc_Key'].strip()
            code = row['ICDPROCEDURECODE'].strip()
            if code not in code_lists['all_locked_px']:
                continue
            try:
                pd = int(float(row['HOSPITALPROCEDURESTARTDAYS'])) if row['HOSPITALPROCEDURESTARTDAYS'] != '' else None
                ph = float(row['HOSPITALPROCEDURESTARTHRS']) if row['HOSPITALPROCEDURESTARTHRS'] != '' else None
            except ValueError:
                pd, ph = None, None
            if code in code_lists['emergent_px']:
                px_flags[enc]['emergent_px'] = 1
            if code in code_lists['orbital_px']:
                px_flags[enc]['orbital_px'] = 1
            px_flags[enc]['codes'].add(code)
            if pd is not None and ph is not None:
                if px_flags[enc]['first_px_day'] is None or (pd, ph) < (px_flags[enc]['first_px_day'], px_flags[enc]['first_px_hr']):
                    px_flags[enc]['first_px_day'] = pd
                    px_flags[enc]['first_px_hr'] = ph
                    px_flags[enc]['first_px_code'] = code
    return px_flags


def build_events_flags():
    ev = defaultdict(lambda: {'major_systemic_complication': 0, 'event_codes': set()})
    with open(FILES['events'], newline='', encoding='utf-8-sig') as f:
        r = csv.DictReader(f)
        for row in r:
            enc = row['Inc_Key'].strip()
            code = row['HOSPITALEVENT'].strip()
            ans = row['HOSPITALEVENTANSWER'].strip()
            if ans == '1' and code in SYSTEMIC_COMPLICATIONS:
                ev[enc]['major_systemic_complication'] = 1
                ev[enc]['event_codes'].add(code)
    return ev


def build_preexist_counts():
    pre = defaultdict(int)
    with open(FILES['preexist'], newline='', encoding='utf-8-sig') as f:
        r = csv.DictReader(f)
        for row in r:
            enc = row['Inc_Key'].strip()
            ans = row['PREEXISTINGCONDITIONANSWER'].strip()
            if ans == '1':
                pre[enc] += 1
    return pre


def main():
    run_ts = datetime.now().isoformat()
    issues = []
    assumptions = [
        'Phase 3 implements the approved clinical decisions received after Phase 2 review.',
        'Primary cohort requires acute, clinically significant mechanical ocular/orbital trauma.',
        'AIS is used primarily as supportive severity/subgroup information rather than a co-equal entry criterion.',
        'Minor/superficial injuries are excluded from the primary cohort unless paired with severe qualifying injury logic.',
        'Primary procedural endpoint is restricted to definitive repair-like operative interventions.',
        'Primary timing cohort is direct-arrival only and anchored by ISS >= 16.',
        'Negative elapsed-time records are exported for review and excluded from the primary continuous timing cohort.',
    ]

    dx_review, px_review, ais_review = load_review_tables()
    code_lists = build_locked_code_lists(dx_review, px_review, ais_review)

    trauma = load_trauma_core()
    dx_flags = build_dx_flags(code_lists)
    ais_flags = build_ais_flags(code_lists)
    px_flags = build_px_flags_and_timing(code_lists)
    ev_flags = build_events_flags()
    pre_counts = build_preexist_counts()

    # Export locked code lists for audit.
    locked_codebook = {
        'emergent_dx': sorted(code_lists['emergent_dx']),
        'orbital_dx': sorted(code_lists['orbital_dx']),
        'excluded_dx': sorted(code_lists['excluded_dx']),
        'emergent_px': sorted(code_lists['emergent_px']),
        'orbital_px': sorted(code_lists['orbital_px']),
        'ais_support': sorted(code_lists['ais_support']),
    }
    (OUT / 'phase3_locked_codebook.json').write_text(json.dumps(locked_codebook, indent=2), encoding='utf-8')

    rows = []
    neg_rows = []
    counts = Counter()
    stratum_counts = Counter()
    first_px_code_counts = Counter()

    for enc, t in trauma.items():
        counts['total_trauma'] += 1
        iss = t['iss']
        if iss is None or iss < 16:
            continue
        counts['iss16'] += 1

        dxf = dx_flags.get(enc, {'emergent_dx':0,'orbital_dx':0,'codes':set()})
        aif = ais_flags.get(enc, {'ais_support':0,'codes':set()})
        pxf = px_flags.get(enc, {'emergent_px':0,'orbital_px':0,'first_px_day':None,'first_px_hr':None,'first_px_code':None,'codes':set()})
        evf = ev_flags.get(enc, {'major_systemic_complication':0,'event_codes':set()})
        pre_n = pre_counts.get(enc, 0)

        if not (dxf['emergent_dx'] or dxf['orbital_dx']):
            continue
        counts['qualifying_dx'] += 1

        # supportive AIS not required but tracked
        if aif['ais_support']:
            counts['ais_supported'] += 1

        if pxf['first_px_code'] is None:
            continue
        counts['qualifying_px'] += 1

        # stratum assignment
        if dxf['emergent_dx'] and not dxf['orbital_dx']:
            stratum = 'emergent_ocular'
        elif dxf['orbital_dx'] and not dxf['emergent_dx']:
            stratum = 'orbital_adnexal'
        elif dxf['emergent_dx'] and dxf['orbital_dx']:
            stratum = 'mixed_emergent_priority'
        else:
            stratum = 'unclassified'

        if t['transfer'] == '1':
            transfer_group = 'transfer'
        elif t['transfer'] == '2':
            transfer_group = 'direct'
        else:
            transfer_group = 'unknown'

        # build primary timing eligibility only for direct arrivals with valid arrival time
        arrival_valid = (transfer_group == 'direct' and t['arrival_day'] is not None and t['arrival_hr'] is not None)
        elapsed_hours = None
        negative_time = 0
        if arrival_valid and pxf['first_px_day'] is not None and pxf['first_px_hr'] is not None:
            elapsed_hours = ((pxf['first_px_day'] - t['arrival_day']) * 24.0) + (pxf['first_px_hr'] - t['arrival_hr'])
            if elapsed_hours < 0:
                negative_time = 1

        row = {
            'inc_key': enc,
            'iss': iss,
            'transfer_group': transfer_group,
            'arrival_valid_for_primary_timing': 1 if arrival_valid else 0,
            'emergent_dx': dxf['emergent_dx'],
            'orbital_dx': dxf['orbital_dx'],
            'ais_support': aif['ais_support'],
            'stratum': stratum,
            'first_px_code': pxf['first_px_code'],
            'first_px_day': pxf['first_px_day'],
            'first_px_hr': pxf['first_px_hr'],
            'elapsed_hours_to_first_px': elapsed_hours,
            'negative_elapsed_time': negative_time,
            'age': t['age'],
            'sex': t['sex'],
            'ethnicity': t['ethnicity'],
            'payer': t['payer'],
            'sbp': t['sbp'],
            'pulse': t['pulse'],
            'rr': t['rr'],
            'temp': t['temp'],
            'spo2': t['spo2'],
            'gcsmotor': t['gcsmotor'],
            'totalgcs': t['totalgcs'],
            'highestactivation': t['highestactivation'],
            'prehosp_arrest': t['prehosp_arrest'],
            'hmrrhgtype': t['hmrrhgtype'],
            'angiography': t['angiography'],
            'major_systemic_complication': evf['major_systemic_complication'],
            'in_hospital_mortality': 1 if t['hospdisp'] == '5' else 0,
            'iculos': t['iculos'],
            'ventdays': t['ventdays'],
            'inpatientdays': t['inpatientdays'],
            'hospdisp': t['hospdisp'],
            'eddisp': t['eddisp'],
            'preexisting_condition_count': pre_n,
            'dx_codes': ';'.join(sorted(dxf['codes'])),
            'ais_codes': ';'.join(sorted(aif['codes'])),
            'px_codes': ';'.join(sorted(pxf['codes'])),
            'systemic_event_codes': ';'.join(sorted(evf['event_codes'])),
        }
        rows.append(row)
        stratum_counts[stratum] += 1
        first_px_code_counts[pxf['first_px_code']] += 1
        counts['locked_rows'] += 1

        if negative_time:
            neg_rows.append(row)
            counts['negative_timing_rows'] += 1

    # Primary timing dataset excludes negatives and non-direct/nonvalid arrivals.
    primary_rows = [r for r in rows if r['arrival_valid_for_primary_timing'] == 1 and r['negative_elapsed_time'] == 0 and r['elapsed_hours_to_first_px'] is not None]
    counts['primary_timing_rows'] = len(primary_rows)

    # Save datasets
    fieldnames = list(rows[0].keys()) if rows else []
    if rows:
        with open(OUT / 'phase3_locked_operable_dataset.csv', 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(rows)
    if primary_rows:
        with open(OUT / 'phase3_primary_timing_dataset.csv', 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(primary_rows)
    if neg_rows:
        with open(OUT / 'phase3_negative_timing_review.csv', 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(neg_rows)

    summary = {
        'run_timestamp': run_ts,
        'assumptions': assumptions,
        'issues': issues,
        'approved_decisions_implemented': {
            'acute_mechanical_dx_priority': True,
            'definitive_repairlike_px_only': True,
            'ais_supportive_not_coequal_entry': True,
            'minor_superficial_excluded': True,
            'emergent_vs_orbital_strata_separate': True,
            'negative_timing_exported_and_excluded_from_primary': True,
            'direct_arrival_primary_timing_only': True,
            'iss16_anchor': True,
        },
        'locked_code_counts': {
            'emergent_dx': len(code_lists['emergent_dx']),
            'orbital_dx': len(code_lists['orbital_dx']),
            'excluded_dx': len(code_lists['excluded_dx']),
            'emergent_px': len(code_lists['emergent_px']),
            'orbital_px': len(code_lists['orbital_px']),
            'ais_support': len(code_lists['ais_support']),
        },
        'dataset_counts': dict(counts),
        'stratum_counts': dict(stratum_counts),
        'top_first_px_codes': first_px_code_counts.most_common(25),
    }

    if counts['negative_timing_rows'] > 0:
        issues.append(f"{counts['negative_timing_rows']} negative elapsed-time records were exported for review and excluded from the primary timing dataset.")
    if counts['primary_timing_rows'] == 0:
        issues.append('Primary timing dataset is empty; final code lists may be too restrictive or timing validity may be inadequate.')

    (OUT / 'phase3_summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    with open(OUT / 'phase3_report.txt', 'w', encoding='utf-8') as f:
        f.write('PHASE 3 LOCKED ANALYTIC DATASET CONSTRUCTION REPORT\n')
        f.write(f'Run timestamp: {run_ts}\n\n')
        f.write('Approved clinical decisions were implemented as rule-based cohort and endpoint logic.\n\n')
        f.write('LOCKED CODE COUNTS\n')
        for k,v in summary['locked_code_counts'].items():
            f.write(f'- {k}: {v}\n')
        f.write('\nDATASET COUNTS\n')
        for k,v in summary['dataset_counts'].items():
            f.write(f'- {k}: {v}\n')
        f.write('\nSTRATUM COUNTS\n')
        for k,v in summary['stratum_counts'].items():
            f.write(f'- {k}: {v}\n')
        f.write('\nMAJOR ISSUES / NOTES\n')
        if issues:
            for item in issues:
                f.write(f'- {item}\n')
        else:
            f.write('- No major unexpected issues recorded in Phase 3.\n')
        f.write('\nOUTPUTS\n')
        f.write('- phase3_locked_codebook.json\n')
        f.write('- phase3_locked_operable_dataset.csv\n')
        f.write('- phase3_primary_timing_dataset.csv\n')
        f.write('- phase3_negative_timing_review.csv (if present)\n')
        f.write('- phase3_summary.json\n')

    (DOC / 'phase3_approved_decisions.txt').write_text('\n'.join(assumptions + ['Issues:', *issues]), encoding='utf-8')
    (LOG / 'phase3_run.log').write_text(json.dumps({'run_timestamp': run_ts, 'issues': issues}, indent=2), encoding='utf-8')

if __name__ == '__main__':
    main()
