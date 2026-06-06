# Impact of Competing Interventions and Timing of Orbital and Adnexal Operative Care in Severe Polytrauma
### Study Supporting Documentation 
Python Scripts and Pipleine. Phases used with TQIP PUF for personal, local, data extraction and visibility. Provided for reproducibility & Auditing. Applied specifically to the [American College of Surgeons 2024 Trauma Quality Improvement Program Participant Use File](https://www.facs.org/quality-programs/trauma/quality/trauma-quality-improvement-program/) data. 
## Pipeline Overview
The code processes raw TQIP data sequentially to define a clinically relevant ocular/orbital trauma cohort and execute statistical models predicting procedural delay.

<details>
<summary><b>Phase descriptions</b></summary>
<br>
  
> Numbering inconsistencies reflect changes made during initial study execution and were preserved for simplicty within py scripts.

<br>
  
  * **Phase 1: Broad Discovery (`phase1_descriptive_build.py`)** 
  First-pass ingestion of raw TQIP files. Uses broad keyword matching to identify candidate diagnoses, procedures, and AIS injury codes, and resolves decimal-hour formatting anomalies in the raw
  timing fields.
  * **Phase 2: Codebook Refinement (`phase2_curated_codebook_build.py`)** 
  Applies heuristic labels (e.g., "repair-like", "orbital/adnexal") to candidate lists to generate scaffolding tables for manual clinical curation.
  * **Phase 3: Cohort Definition & Dataset Lock (`phase3_locked_dataset_build.py`)** 
  Translates clinical decisions into strict logic. Enforces study inclusion/exclusion criteria (ISS ≥ 16, direct arrivals, timing exclusions) to build the locked operable dataset and primary
  timing cohort.
  * **Phase 3.5: Face-Validity Check (`phase35_face_validity_review.py`)** 
  Pre-modeling sanity check. Validates cohort distributions, confirming the necessity of restricting the analysis to an orbital/adnexal-dominant population due to sample size realities.
  * **Phase 4 & 6: Descriptive Statistics (`phase4_descriptive_tables.py`)** 
  Generates baseline characteristics, calculating medians, IQRs, counts, and covariate completeness for the restricted, model-ready cohort. Phase 5 skipped. 
  * **Phase 7: Site Merging & Refinement Prep (`phase7_prepare_refinement_plan.py`)** 
  Merges the center-level identifier (`TQIPSITE`) into the primary dataset and heuristically categorizes negative timing cases for transparent auditing.
  * **Phase 8: Final Parsimonious Modeling (`phase8_final_parsimonious_models.py`)** 
  Executes the multivariable logistic regression (using the cohort median as the threshold for "prolonged delay") and log-time sensitivity models.
  
</details>
  
## Methodological Notes for Auditors
* **Cohort Framing:** The final usable cohort is overwhelmingly orbital/adnexal; isolated emergent ocular cases were too rare for stable independent modeling.
* **Negative Timing Cases:** Cases with negative arrival-to-procedure times were intentionally excluded from main models but are categorized internally for audit transparency.
* **Site Clustering:** While `TQIPSITE` was evaluated, severe center-level imbalances in the restricted cohort made cluster-robust standard errors technically unstable. Unclustered models were favored for stability.

## Study Concept & Aim 
This study looked at severely injured trauma patients in a large national trauma registry to understand what affects how long it takes for someone with serious eye, orbital, or surrounding facial injuries to get to a meaningful eye-related operation. Eye and orbital surgery may often be delayed and we this study attempted to see if there was a link to overall severity of injury and competing procedures vs. the actual injury. 

> [!Important]
> Statistically, the code compares patients who had a longer-than-typical delay to surgery with those who had a shorter delay, and we also ran a second model treating time to surgery as a continuous measure; these models adjusted for factors like age, overall injury severity, neurologic status, hemorrhage-control surgery, and angiography to see which factors were independently associated with delay.


## Data Privacy & Reproducibility Notice
To comply with the American College of Surgeons (ACS) TQIP Data Use Agreement, **no patient-level data, raw PUF files, or frozen intermediate datasets are included in this repository.** 

Researchers seeking to reproduce this study or audit the code must independently obtain the TQIP PUF datasets from the ACS, place the raw data in the designated local input directories, and execute this pipeline. Output files provided in this repository are strictly limited to aggregated analytical logs. 

<hr>

Corresponding Author Contact: 
```diff
+ Khanzs@odu.edu 
```
