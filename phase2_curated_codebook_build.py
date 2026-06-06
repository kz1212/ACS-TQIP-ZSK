#!/usr/bin/env python3
import csv, json, re, math
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime

BASE = Path('/Users/___/Desktop/PUF AY 2024/CSV')
WORK = Path('/Users/___/Desktop/tqip_ocular_study_phase2')
OUT = WORK / 'outputs'
LOG = WORK / 'logs'
DOC = WORK / 'docs'

FILES = {
    'trauma': BASE / 'PUF_TRAUMA.csv',
    'icd_dx': BASE / 'PUF_ICDDIAGNOSIS.csv',
    'icd_dx_lookup': BASE / 'PUF_ICDDIAGNOSIS_LOOKUP.csv',
    'icd_px': BASE / 'PUF_ICDPROCEDURE.csv',
    'icd_px_lookup': BASE / 'PUF_ICDPROCEDURE_LOOKUP.csv',
    'ais': BASE / 'PUF_AISDIAGNOSIS.csv',
    'ais_lookup': BASE / 'PUF_AISDIAGNOSIS_LOOKUP.csv',
}

# Heuristic keyword sets for transparent review triage only.
DX_INCLUDE_TERMS = [
    'rupture', 'laceration', 'penetrating', 'perforat', 'enucleat', 'avulsion',
    'optic nerve', 'open wound', 'fracture of orbit', 'orbital floor', 'orbital roof',
    'orbital wall', 'blowout', 'retrobulbar', 'canalicul', 'lacrimal', 'retained intraocular foreign body',
    'foreign body in', 'foreign body on external eye', 'hyphema', 'sclera', 'cornea', 'retina', 'globe',
    'injury of eye', 'injury of optic nerve', 'injury of conjunctiva'
]
DX_EXCLUDE_TERMS = [
    'subsequent encounter', 'sequela', 'routine', 'history of', 'family history', 'screening',
    'without abnormal findings', 'congenital', 'neoplasm', 'diabetic', 'glaucoma', 'cataract', 'retinopathy',
    'conjunctivitis', 'blepharitis', 'degeneration', 'atrophy', 'chronic', 'prosthetic', 'postprocedural',
    'infection', 'ulcer', 'keratitis', 'pterygium', 'dry eye', 'examination'
]
DX_MINOR_TERMS = [
    'contusion of eyelid', 'superficial', 'abrasion', 'minor', 'hematoma', 'periocular area'
]

PX_ACTION_TERMS = [
    'repair ', 'reposition ', 'replacement ', 'supplement ', 'drainage ', 'extirpation ',
    'removal ', 'excision ', 'destruction ', 'release ', 'insertion of internal fixation'
]
PX_STRUCTURE_TERMS = [
    'eye', 'orbit', 'orbital', 'eyelid', 'lacrimal duct', 'lacrimal bone', 'extraocular muscle',
    'sclera', 'cornea', 'retina', 'choroid', 'optic nerve', 'conjunctiva', 'vitreous'
]
PX_EXCLUDE_TERMS = [
    'inspection', 'computerized tomography', 'plain radiography', 'magnetic resonance imaging',
    'ultrasonography', 'introduction of', 'diagnostic', 'revision of', 'removal of device',
    'prosthesis', 'prosthetic', 'monitoring', 'plain radiography', 'ct scan'
]
PX_REPAIRLIKE_TERMS = [
    'repair ', 'reposition ', 'replacement ', 'supplement ', 'drainage ', 'extirpation ', 'insertion of internal fixation'
]

AIS_INCLUDE_TERMS = [
    'optic nerve', 'eye avulsion', 'enucleation', 'canaliculus', 'conjunctiva injury', 'cornea',
    'retina', 'lens', 'choroid', 'intraocular foreign body', 'orbit fracture', 'retrobulbar', 'globe'
]
AIS_EXCLUDE_TERMS = [
    'minor; superficial', 'abrasion', 'contusion; hematoma', 'skin/subcutaneous/muscle, face', 'nfs'
]

MCI_TERMS = [
    'laparotomy', 'thoracotomy', 'sternotomy', 'craniotomy', 'craniectomy', 'embolization', 'angiography',
    'fixation of femur', 'fixation of tibia', 'fixation of humerus', 'spinal fusion', 'pelvic packing',
    'vascular', 'splenectomy', 'hepatorrhaphy', 'bowel resection'
]


def normalize(s):
    return re.sub(r'\s+', ' ', (s or '').strip().lower())


def count_rows(path):
    with open(path, newline='', encoding='utf-8-sig') as f:
        return sum(1 for _ in f) - 1


def load_lookup(path, code_key, desc_key):
    rows = []
    with open(path, newline='', encoding='utf-8-sig') as f:
        r = csv.DictReader(f)
        for row in r:
            code = row[code_key].strip()
            desc = row[desc_key].strip()
            rows.append({'code': code, 'description': desc})
    return rows


def classify_dx(desc):
    d = normalize(desc)
    include = any(t in d for t in DX_INCLUDE_TERMS)
    exclude = any(t in d for t in DX_EXCLUDE_TERMS)
    minor = any(t in d for t in DX_MINOR_TERMS)
    if exclude:
        triage = 'exclude_nonacute_or_nonspecific'
    elif include and minor:
        triage = 'review_minor_or_mixed'
    elif include:
        triage = 'candidate_include_review'
    elif minor:
        triage = 'exclude_minor_superficial'
    else:
        triage = 'review_other'

    if any(x in d for x in ['globe', 'optic nerve', 'intraocular', 'retina', 'sclera', 'cornea', 'hyphema', 'enucleat', 'avulsion']):
        stratum = 'emergent_ocular_candidate'
    elif any(x in d for x in ['orbit', 'orbital', 'eyelid', 'lacrimal', 'canalicul', 'periocular']):
        stratum = 'orbital_adnexal_candidate'
    else:
        stratum = 'unclassified'
    return triage, stratum


def classify_px(desc):
    d = normalize(desc)
    has_action = any(t in d for t in PX_ACTION_TERMS)
    has_structure = any(t in d for t in PX_STRUCTURE_TERMS)
    exclude = any(t in d for t in PX_EXCLUDE_TERMS)
    repairlike = any(t in d for t in PX_REPAIRLIKE_TERMS)

    if exclude:
        triage = 'exclude_diagnostic_or_nondefinitive'
    elif has_action and has_structure and repairlike:
        triage = 'candidate_include_repairlike'
    elif has_action and has_structure:
        triage = 'candidate_include_review'
    else:
        triage = 'review_other'

    if any(x in d for x in ['globe', 'optic nerve', 'retina', 'sclera', 'cornea', 'choroid', 'vitreous', 'eye']) and 'eyelid' not in d and 'orbit' not in d and 'lacrimal' not in d:
        stratum = 'emergent_ocular_candidate'
    elif any(x in d for x in ['orbit', 'orbital', 'eyelid', 'lacrimal', 'canalicul', 'extraocular muscle']):
        stratum = 'orbital_adnexal_candidate'
    else:
        stratum = 'mixed_or_unclassified'

    mci_hint = 'yes' if any(t in d for t in MCI_TERMS) else 'no'
    return triage, stratum, repairlike, mci_hint


def classify_ais(desc):
    d = normalize(desc)
    include = any(t in d for t in AIS_INCLUDE_TERMS)
    exclude = any(t in d for t in AIS_EXCLUDE_TERMS)
    if exclude:
        triage = 'exclude_minor_or_nonspecific'
    elif include:
        triage = 'candidate_include_review'
    else:
        triage = 'review_other'

    if any(x in d for x in ['optic nerve', 'eye avulsion', 'enucleation', 'retina', 'cornea', 'lens', 'intraocular foreign body', 'globe']):
        stratum = 'emergent_ocular_candidate'
    elif any(x in d for x in ['orbit fracture', 'canaliculus', 'conjunctiva injury', 'eyelid']):
        stratum = 'orbital_adnexal_candidate'
    else:
        stratum = 'unclassified'
    return triage, stratum


def write_csv(path, rows, fieldnames):
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in rows:
            w.writerow(row)


def main():
    run_ts = datetime.now().isoformat()
    issues = []
    assumptions = [
        'Phase 2 produces clinician-review code tables using explicit heuristic triage labels; these are not final clinical definitions.',
        'Phase 2 preliminary refined counts are exploratory and depend on heuristic include/exclude rules that must be reviewed before Phase 3.',
        'Diagnostic-only ocular/orbital procedures should not define the final procedural timing endpoint.',
        'Direct-arrival timing remains the intended primary analytic framework for later phases.',
        'Corrected Phase 2 rerun: INTERFACILITYTRANSFER is interpreted as 1=transfer and 2=not transfer/direct arrival based on observed file values.',
        'Corrected Phase 2 rerun: procedure heuristics require both an operative action term and an ocular/orbital structure term, with diagnostic-only terms excluded.',
    ]

    # Load lookups and classify.
    dx_lookup = load_lookup(FILES['icd_dx_lookup'], 'ICDDIAGNOSISCODE', 'ICDDiagnosisCode_Desc')
    px_lookup = load_lookup(FILES['icd_px_lookup'], 'ICDPROCEDURECODE', 'ICDProcedureCode_Desc')
    ais_lookup = load_lookup(FILES['ais_lookup'], 'AISPREDOT', 'AISDESCRIPTION')

    dx_rows = []
    dx_include_codes = set()
    dx_exclude_codes = set()
    for row in dx_lookup:
        triage, stratum = classify_dx(row['description'])
        out = {'code': row['code'], 'description': row['description'], 'triage_label': triage, 'stratum_hint': stratum}
        dx_rows.append(out)
        if triage in {'candidate_include_review', 'review_minor_or_mixed'}:
            dx_include_codes.add(row['code'])
        elif triage in {'exclude_nonacute_or_nonspecific', 'exclude_minor_superficial'}:
            dx_exclude_codes.add(row['code'])

    px_rows = []
    px_include_codes = set()
    px_repairlike_codes = set()
    for row in px_lookup:
        triage, stratum, repairlike, mci_hint = classify_px(row['description'])
        out = {'code': row['code'], 'description': row['description'], 'triage_label': triage, 'stratum_hint': stratum, 'repairlike_hint': 'yes' if repairlike else 'no', 'mci_hint': mci_hint}
        px_rows.append(out)
        if triage in {'candidate_include_repairlike', 'candidate_include_review'}:
            px_include_codes.add(row['code'])
        if triage == 'candidate_include_repairlike':
            px_repairlike_codes.add(row['code'])

    ais_rows = []
    ais_include_codes = set()
    for row in ais_lookup:
        triage, stratum = classify_ais(row['description'])
        out = {'code': row['code'], 'description': row['description'], 'triage_label': triage, 'stratum_hint': stratum}
        ais_rows.append(out)
        if triage == 'candidate_include_review':
            ais_include_codes.add(row['code'])

    # Save clinician-review tables.
    write_csv(OUT / 'phase2_dx_review_table.csv', dx_rows, ['code', 'description', 'triage_label', 'stratum_hint'])
    write_csv(OUT / 'phase2_px_review_table.csv', px_rows, ['code', 'description', 'triage_label', 'stratum_hint', 'repairlike_hint', 'mci_hint'])
    write_csv(OUT / 'phase2_ais_review_table.csv', ais_rows, ['code', 'description', 'triage_label', 'stratum_hint'])

    # Preliminary refined encounter counts.
    dx_enc = set()
    dx_stratum_counter = Counter()
    top_dx = Counter()
    dx_desc_map = {r['code']: r['description'] for r in dx_rows}
    dx_stratum_map = {r['code']: r['stratum_hint'] for r in dx_rows if r['triage_label'] in {'candidate_include_review', 'review_minor_or_mixed'}}
    with open(FILES['icd_dx'], newline='', encoding='utf-8-sig') as f:
        r = csv.DictReader(f)
        for row in r:
            code = row['ICDDIAGNOSISCODE'].strip()
            if code in dx_include_codes and code not in dx_exclude_codes:
                enc = row['Inc_Key'].strip()
                dx_enc.add(enc)
                top_dx[code] += 1
                dx_stratum_counter[dx_stratum_map.get(code, 'unclassified')] += 1

    ais_enc = set()
    top_ais = Counter()
    ais_desc_map = {r['code']: r['description'] for r in ais_rows}
    with open(FILES['ais'], newline='', encoding='utf-8-sig') as f:
        r = csv.DictReader(f)
        for row in r:
            code = row['AISPreDot'].strip()
            if code in ais_include_codes:
                enc = row['inc_key'].strip()
                ais_enc.add(enc)
                top_ais[code] += 1

    px_enc = set()
    px_repair_enc = set()
    top_px = Counter()
    px_desc_map = {r['code']: r['description'] for r in px_rows}
    with open(FILES['icd_px'], newline='', encoding='utf-8-sig') as f:
        r = csv.DictReader(f)
        for row in r:
            code = row['ICDPROCEDURECODE'].strip()
            enc = row['Inc_Key'].strip()
            if code in px_include_codes:
                px_enc.add(enc)
                top_px[code] += 1
            if code in px_repairlike_codes:
                px_repair_enc.add(enc)

    # Trauma-level severe/direct/transfer counts
    severe_enc = set()
    direct_enc = set()
    transfer_enc = set()
    valid_arrival = set()
    with open(FILES['trauma'], newline='', encoding='utf-8-sig') as f:
        r = csv.DictReader(f)
        for row in r:
            enc = row['inc_key'].strip()
            try:
                iss = int(float(row['ISS'])) if row['ISS'] != '' else None
            except ValueError:
                iss = None
            if iss is not None and iss >= 16:
                severe_enc.add(enc)
            tr = row['INTERFACILITYTRANSFER'].strip()
            if tr == '1':
                transfer_enc.add(enc)
            elif tr == '2':
                direct_enc.add(enc)
            try:
                ad = int(float(row['HOSPITALARRIVALDAYS'])) if row['HOSPITALARRIVALDAYS'] != '' else None
                ah = float(row['HOSPITALARRIVALHRS']) if row['HOSPITALARRIVALHRS'] != '' else None
            except ValueError:
                ad, ah = None, None
            if ad is not None and ah is not None:
                valid_arrival.add(enc)

    refined_union = dx_enc | ais_enc
    severe_refined = refined_union & severe_enc
    severe_operable = severe_refined & px_enc
    severe_repairlike = severe_refined & px_repair_enc
    direct_severe_repairlike = severe_repairlike & direct_enc
    transfer_severe_repairlike = severe_repairlike & transfer_enc
    direct_severe_repairlike_valid_arrival = direct_severe_repairlike & valid_arrival

    # Timing QC for repairlike only.
    earliest_px = {}
    invalid_px_time_rows = 0
    with open(FILES['icd_px'], newline='', encoding='utf-8-sig') as f:
        r = csv.DictReader(f)
        for row in r:
            code = row['ICDPROCEDURECODE'].strip()
            if code not in px_repairlike_codes:
                continue
            enc = row['Inc_Key'].strip()
            try:
                pd = int(float(row['HOSPITALPROCEDURESTARTDAYS'])) if row['HOSPITALPROCEDURESTARTDAYS'] != '' else None
                ph = float(row['HOSPITALPROCEDURESTARTHRS']) if row['HOSPITALPROCEDURESTARTHRS'] != '' else None
            except ValueError:
                pd, ph = None, None
            if pd is None or ph is None:
                invalid_px_time_rows += 1
                continue
            current = (pd, ph, code)
            if enc not in earliest_px or (pd, ph) < (earliest_px[enc][0], earliest_px[enc][1]):
                earliest_px[enc] = current

    trauma_arrival = {}
    with open(FILES['trauma'], newline='', encoding='utf-8-sig') as f:
        r = csv.DictReader(f)
        for row in r:
            enc = row['inc_key'].strip()
            if enc not in direct_severe_repairlike_valid_arrival:
                continue
            try:
                ad = int(float(row['HOSPITALARRIVALDAYS'])) if row['HOSPITALARRIVALDAYS'] != '' else None
                ah = float(row['HOSPITALARRIVALHRS']) if row['HOSPITALARRIVALHRS'] != '' else None
            except ValueError:
                ad, ah = None, None
            if ad is not None and ah is not None:
                trauma_arrival[enc] = (ad, ah)

    elapsed = []
    neg = zero = pos = 0
    for enc in direct_severe_repairlike_valid_arrival:
        if enc not in earliest_px or enc not in trauma_arrival:
            continue
        ad, ah = trauma_arrival[enc]
        pd, ph, code = earliest_px[enc]
        hrs = ((pd - ad) * 24.0) + (ph - ah)
        elapsed.append(hrs)
        if hrs < 0:
            neg += 1
        elif hrs == 0:
            zero += 1
        else:
            pos += 1

    elapsed_sorted = sorted(elapsed)
    elapsed_summary = {
        'n': len(elapsed_sorted),
        'min': elapsed_sorted[0] if elapsed_sorted else None,
        'median': elapsed_sorted[len(elapsed_sorted)//2] if elapsed_sorted else None,
        'max': elapsed_sorted[-1] if elapsed_sorted else None,
    }

    if neg > 0:
        issues.append(f'Refined repair-like timing still yields {neg} negative elapsed-hour values, indicating remaining code/timing misalignment that must be reviewed before Phase 3.')
    if len(top_px) > 0:
        top_first = top_px.most_common(10)
        if any('inspection' in normalize(px_desc_map[c]) or 'computerized tomography' in normalize(px_desc_map[c]) for c,_ in top_first):
            issues.append('Unexpected diagnostic procedures remain among top preliminary included ocular/orbital procedures; heuristic inclusion may still be too broad and needs review.')

    summary = {
        'run_timestamp': run_ts,
        'files': {k: {'path': str(v), 'rows': count_rows(v)} for k, v in FILES.items()},
        'assumptions': assumptions,
        'issues': issues,
        'heuristic_counts': {
            'dx_candidate_include_codes': len(dx_include_codes),
            'px_candidate_include_codes': len(px_include_codes),
            'px_repairlike_codes': len(px_repairlike_codes),
            'ais_candidate_include_codes': len(ais_include_codes),
        },
        'preliminary_refined_counts': {
            'refined_dx_candidate_encounters': len(dx_enc),
            'refined_ais_candidate_encounters': len(ais_enc),
            'refined_union_candidate_encounters': len(refined_union),
            'refined_px_candidate_encounters': len(px_enc),
            'refined_repairlike_px_encounters': len(px_repair_enc),
            'severe_refined_candidate_encounters': len(severe_refined),
            'severe_operable_candidate_encounters': len(severe_operable),
            'severe_repairlike_candidate_encounters': len(severe_repairlike),
            'direct_severe_repairlike_candidate_encounters': len(direct_severe_repairlike),
            'transfer_severe_repairlike_candidate_encounters': len(transfer_severe_repairlike),
            'direct_severe_repairlike_with_valid_arrival': len(direct_severe_repairlike_valid_arrival),
        },
        'timing_qc_repairlike': {
            'invalid_repairlike_px_time_rows': invalid_px_time_rows,
            'elapsed_negative_count': neg,
            'elapsed_zero_count': zero,
            'elapsed_positive_count': pos,
            'elapsed_summary': elapsed_summary,
        },
        'top_codes': {
            'diagnosis': [{'code': c, 'n': n, 'description': dx_desc_map.get(c, '')} for c, n in top_dx.most_common(30)],
            'procedure': [{'code': c, 'n': n, 'description': px_desc_map.get(c, '')} for c, n in top_px.most_common(30)],
            'ais': [{'code': c, 'n': n, 'description': ais_desc_map.get(c, '')} for c, n in top_ais.most_common(30)],
        }
    }

    (OUT / 'phase2_summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    (OUT / 'phase2_top_dx_codes.json').write_text(json.dumps(summary['top_codes']['diagnosis'], indent=2), encoding='utf-8')
    (OUT / 'phase2_top_px_codes.json').write_text(json.dumps(summary['top_codes']['procedure'], indent=2), encoding='utf-8')
    (OUT / 'phase2_top_ais_codes.json').write_text(json.dumps(summary['top_codes']['ais'], indent=2), encoding='utf-8')

    with open(OUT / 'phase2_report.txt', 'w', encoding='utf-8') as f:
        f.write('PHASE 2 CURATED CODEBOOK AND COHORT-DEFINITION BUILD REPORT\n')
        f.write(f'Run timestamp: {run_ts}\n\n')
        f.write('Scope note: Phase 2 applies transparent heuristic triage labels for clinician review. These labels support codebook refinement and preliminary cohort discovery only; they do not establish final study definitions.\n\n')
        f.write('HEURISTIC CODE COUNTS\n')
        for k,v in summary['heuristic_counts'].items():
            f.write(f'- {k}: {v}\n')
        f.write('\nPRELIMINARY REFINED COUNTS\n')
        for k,v in summary['preliminary_refined_counts'].items():
            f.write(f'- {k}: {v}\n')
        f.write('\nREPAIR-LIKE TIMING QC\n')
        for k,v in summary['timing_qc_repairlike'].items():
            f.write(f'- {k}: {v}\n')
        f.write('\nMAJOR ISSUES / NOTES\n')
        if issues:
            for item in issues:
                f.write(f'- {item}\n')
        else:
            f.write('- No major unexpected issues recorded in Phase 2.\n')
        f.write('\nIMPORTANT NEXT STEP\n')
        f.write('- Clinician review and approval of diagnosis, procedure, AIS, and exclusion tables are required before Phase 3 analytic dataset construction.\n')

    (DOC / 'phase2_assumptions.txt').write_text('\n'.join(assumptions + ['Issues:', *issues]), encoding='utf-8')
    (LOG / 'phase2_run.log').write_text(json.dumps({'run_timestamp': run_ts, 'issues': issues}, indent=2), encoding='utf-8')

if __name__ == '__main__':
    main()
