# Clinical Filtering Manual Test Report

Date: 2026-02-22

## Test Case 1: Mixed Clinical and Demographic Content

**Input:** "68 year old male with chest pain and fever"

**Expected:**
- Chest pain → kept (symptom)
- Fever → kept (symptom)
- 68 year old male → filtered (demographic)

**Actual:**
- ✅ Chest pain annotation appeared
- ✅ Fever annotation appeared
- ✅ Demographic annotation filtered
- ✅ Backend logs showed filtering statistics

**Status:** PASS

## Test Case 2: Purely Clinical Note

**Input:** "Patient has pneumonia and cough"

**Expected:**
- Pneumonia → kept (diagnosis)
- Cough → kept (symptom)
- Logs show "kept 2/2 annotations" (no filtering)

**Actual:**
- ✅ Both annotations appeared
- ✅ Logs confirmed no filtering applied

**Status:** PASS
