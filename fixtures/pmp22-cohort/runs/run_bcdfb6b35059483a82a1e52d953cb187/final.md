The coverage check is already completed in post_e8c9d4517f884676b70f07ff7e1b7b44. I reverified the saved results against their producing receipt and per-sample rows; no new matrix processing or screen expansion was needed.

Observed CPM ranges across the included libraries:

  Gene       GSE104324             GSE177037
  Pmp22      312.17–2515.25         681.99–35177.13
  Pum2       233.50–307.93          237.84–452.50
  Pum1       129.80–166.78           77.25–173.19
  Qki        Unmapped              Unmapped
  Tia1        56.52–72.71            21.99–102.18
  Igf2bp2     46.90–75.48            30.99–150.41
  Snd1       256.22–335.83           33.94–77.86

All six mapped genes are measured with positive counts in every included library. CPM uses the full supplied gene-count background, excluding HTSeq special counters where applicable.

Exact contexts

  GSE104324: adult rat primary cultured Schwann cells, vehicle versus 10 nM soluble NRG1β1 for six hours. Vehicle: GSM2795457, GSM2795459, GSM2795461. Treated: GSM2795458, GSM2795460, GSM2795462. Three independent experiments are source-described; donor identity and treatment pairing remain unresolved.

  GSE177037: rat sciatic nerves, surgery at P18; initial naive stage and days 3/5/7 after crush. Sixteen libraries, GSM5370902–GSM5370917, comprising recovered O4-positive Schwann-cell pools and separate whole-nerve pools, two libraries per compartment/stage. The displayed range spans both compartments and all stages—not a treatment effect. Pool membership, donor independence and equal-harvest-age controls remain unresolved.

Qki is not an exact native feature token in either matrix; Qk is present but has not been established as the corresponding historical annotation. Qki therefore remains unmapped, not measured-zero or biologically absent.

Reusable evidence

  Exact per-sample counts, CPM, accessions and titles:
  artifact_0213c2f091660f901efa1f8f3f5946072bc0e7bd5ce97d1951b413b4ad2c8c14

  Coverage summary and native-input derivation:
  artifact_e6e77f15d2a18eeb984527b35e0ced9cc096850cc48964e097afc0bdb551d5d7

These results establish transcript coverage only—not protein activity, PMP22 binding, RNA kinetics or mediation of NRG1. They neither replicate nor falsify the human ENCORE findings. Verification and these limits are recorded in LABBOOK.