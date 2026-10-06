# Upstream EGR2/PMP22 mediation audit

Question q_59708481fed741af. Author: agent_2a95fafb692f4546b628ba410393d5b1.

## Answer and changed position

The audited evidence establishes a neddylation-sensitive EGR2 persistence mechanism in a defined rat Schwann-cell chase, but does not identify how much of the PMP22 response it mediates. I revise the proposed starting preference toward pleiotropic regulator control with unresolved PMP22 mediation. The crucial prior-source result is PMC11014456 Figure 8N: MG132 restores EGR2 abundance without restoring MPZ. This is neither an EGR2-specific rescue nor a PMP22 promoter experiment. It weakens an abundance-only sufficiency model; it does not prove that active EGR2 restoration would fail, or that EGR2 is unimportant.

This is an audit and retrospective data reuse, not an independent replication or discovery of a new mechanism. Thirteen intervention/assay contexts are tabulated; none jointly supplies selective restoration of EGR2 activity under neddylation loss and matched Pmp22 initiation. Numerical EGR2 half-life and the EGR2-mediated fraction of the Pmp22 effect remain null, not zero.

## What Figures 5–8 actually test

Source: Ayuso-García et al., Science Advances 10:eadm7600 (2024), DOI 10.1126/sciadv.adm7600, PMC11014456. Primary XML hash 4905084f5db89ba5bfdcb3d68821eb82e62740bc574b429faecad960237775b7; downloaded main PDF hash fe184f9cd2aa618216a51d30d1a9f726b8b284ebb703ed8ff277b98f69e12a57. See intervention-by-endpoint.tsv for full locators, doses, units, endpoint definitions and caveats.

- Figure 8K–L: primary rat Schwann cells receive 48 h db cAMP induction, then CHX with vehicle or MLN4924. Methods specify db cAMP 1 mM, CHX 5 µM and MLN4924 2.5 µM. EGR2 disappears faster with MLN4924; ZEB2 does not show that effect. Beta-actin is the loading control. Figure n=3 does not identify three independent rat donors. PDF p13 OCR reads EGR2 chase labels 0,3,6,12,24,48 h and ZEB2 0,3,6,12,24 h; these are OCR-supported labels, not extracted densitometry or a fitted half-life. Native replicate values, activity, matched RNA and viability/synthesis-blockade calibration were not recovered. A CHX chase is more informative about persistence than a steady-state RNA correlation, but still conditional on the chase system.
- Figure 8H–J,M: NEDD8 capture and reciprocal IP, with nonbinding resin, drug sensitivity, input and IgG controls, support modification-associated EGR2 stabilization. EGR2-associated ubiquitin increases with MLN4924. They do not identify a causal neddylation site or an EGR2-specific E3 ligase. Non-denaturing capture does not alone exclude associated proteins. Results call the NEDP1 CA resin catalytically active while Methods specifies C163A; the source inconsistency is retained.
- Figure 8N: MG132 1 µM restores total EGR2, not MPZ to the differentiation-control level. Exact panel exposure duration was not located in retrieved main-text methods. Restored nuclear binding/transactivation, selective EGR2 intervention, and Pmp22 initiation are absent. Proteasome inhibition cannot be treated as an EGR2-specific instrument.
- Figure 5: rapamycin suppresses elevated p-4EBP1 but does not rescue MPZ or myelinated axons in the tested Nae1 context. Mouse treatment is 5 µg/g daily over P5–P10; culture concentration 100 ng/ml. This argues against sufficiency of correcting this branch alone, not against all mTOR contributions.
- Figure 6: XMU-MP-1 reduces abnormal pathway phosphorylation in cultured cells but does not restore MPZ; the in vivo rescue also fails. Doses are 2.5 µM in culture and 5 mg/kg in mice over P5–P10. Phosphorylation correction is not identical to full YAP transcriptional restoration.
- Figure 7: c-Jun and Sox2 proteins persist despite their RNA decreases. CHX shows prolonged c-Jun persistence but no detected Sox2 decay change; the latter suggests rather than proves altered translation. Separate c-Jun/Sox2 knockdown does not rescue MPZ. RNA abundance was measured, not directly nascent transcription.

The source's S6 cross-pathway checks are described in its main text: other branches largely remain altered during single-branch rescues. I could not independently inspect the supplementary PDF. The main-source negative rescues and authors' parallel-pathway interpretation are retained without upgrading them to quantified PMP22 mediation.

## Sample and endpoint eligibility

P7 Nae1 mouse whole-nerve RNA, P28 protein panels, P10 rescue outcomes and rat culture chases are not sample-matched. PXD043917 identification evidence does not supply the missing quantitative protein export, and Figure 7's P7 versus Methods/PRIDE P15 age conflict persists. MPZ is not PMP22; total PMP22 is not its promoter output; nuclear EGR2 abundance is not binding or transactivation. The source also distinguishes differentiation onset from maintenance: its main text reports little mature-myelin/MPZ effect after adult deletion or after prior differentiation (S3, not directly re-inspected). Those windows must not be pooled.

## Executed GSE201623 counterexample

Reused artifact_ae47d75299e31396b253c089db31ef6a95911ffab74697818aa7dcda5135160a only after validating its derivation and every original cell/source-row against native input b3d15fe88a6a680290cb57a382ac93c9f5451966d5d20b58bfa2994b0ddcb580. The preparation faithfully preserves 17,950 rows, including one embedded header at source row 1472; that header was retained in the audit and explicitly excluded from numerical analysis. There are 17,949 numeric features and 13,610 positive in all four libraries. No data tokens were silently coerced and no gene zeros were recoded as missing.

GSM6068774/775 are GFP-labelled controls and GSM6068776/777 AS-labelled libraries. Metadata specifies primary rat sciatic-nerve Schwann cells, 48 h treatment, literal viral dose 2UFC/cell, 10% FBS, forskolin 4 µM and heregulin-β1 5 ng/ml. It calls samples biological replicates, but supplies no verified donor/pool map. Assembly is rn6; GEO says GSNAP, while the 2024 article describes hisat2. Neither annotation is silently replaced. This is gene-assigned total RNA, not a promoter or protein assay.

AS/GFP descriptive log2 ratios of normalized arithmetic group means:

| Gene | Original counts, AS1 / AS2 / GFP1 / GFP2 | Raw | CPM | Median ratio |
|---|---|---:|---:|---:|
| Egr2 | 5364 / 4057 / 4591 / 3995 | +0.134 | +0.366 | +0.331 |
| Pmp22 | 220643 / 201051 / 267997 / 282624 | -0.385 | -0.141 | -0.176 |
| Jun | 78468 / 81462 / 118479 / 107919 | -0.501 | -0.251 | -0.286 |

All three direction patterns survive the declared normalizations. No p-value, confidence interval or donor-level inference is attached. Whole-universe QC and all effects are saved. The AS2 globin-rich anomaly is retained (e.g. Hbb 125355 versus 323 in AS1), without diagnosing its biological origin or dropping the library.

PMC5800313 Figure 5A reports reduced nascent Egr2 transcription after AS expression, whereas these deposited steady-state counts increase. Its Figure 4 reports preservation of PMP22 protein by AS GapMer after adult mouse nerve injury. Neither is a matched Nae1/EGR2 rescue. PMC11592338 §§3.3–3.5 reports AS-induced EGR2 protein loss and C-JUN activation; EGR2 siRNA alone does not reproduce C-JUN activation. That further undermines use of AS inhibition as an EGR2-specific rescue. The deposited Jun RNA decline is also directionally unlike the related protein/activity reports. These are unresolved cross-assay/context inconsistencies, not proof of altered RNA decay, translation, sample mislabelling or erroneous papers.

Primary AS sources: PMC5800313 HTML hash 8b0271c912e5a40eee46fc5328862e7b2f56a3dddd31ef8139e7d5a8ce1069b0; PMC11592338 XML hash febf649b6685ed045eea6758490f75fd8c5bdd37841a1500481b9888116c29bb. Original sample SOFT hash cc3f098b687c26493f4095548b1f9822259f92ac30f26ef5b5d470b5ec8f924b.

## Falsifiable next contrast

The complete proposed test is inputs/rescue-test.json. Use donor-labelled sister Schwann cultures, separating differentiation onset from the already-induced state, with vehicle, upstream perturbation, selective EGR2 restoration, and their combination. Confirm persistent upstream target engagement, control-range nuclear EGR2 AND binding/transactivation; include expression-only and DNA-binding-deficient controls. No validated EGR2 neddylation-site mutant or selective stabilizer is assumed to exist.

At proposed times 0,1,3,6,12,24,48 h, measure Egr2 nascent/mature RNA, EGR2 protein/activity, validated Pmp22 promoter-specific nascent RNA, total RNA, state, viability and alternative pathways. Prefer the earliest eligible window before state divergence; later protein/localization endpoints remain separate. Recovery of initiation with active EGR2 alone supports sufficiency in that window. Persistent initiation loss despite verified restoration supports a parallel contribution. Failure to restore EGR2 activity makes the contrast untestable, not evidence against mediation. Report controlled restoration effects, not an automatic natural mediated fraction. A subsequent Nrf2 factorial arm can separate antioxidant engagement from EGR2 dependence.

## Provenance, negatives and stopping reason

Prior results materially changed the analysis: the corrected protein-export blocker prevented invented LFQ/half-life calculations; missing donor provenance prevented inferential RNA testing; failed normal-atlas mixture calibration prevented causal state adjustment. Figure 8N changed the biological preference. Retrieval is not independent replication.

All inherited negative/untestable outcomes remain in LABBOOK.md, including the failed Pmp22-myelin relative-preservation prediction and the untestable original five-gene antioxidant lock. Nothing here rescues them or establishes NRF2 mediation/human transfer.

RNA execution r001 failed on the embedded header; corrected r002 succeeded with unchanged producer and matching output hashes. The independent tabulation producer validates source locators, IDs, null semantics and RNA receipts. Lint passed. HTTP failures, the inaccessible supplement and OCR-only time labels are preserved. PROVENANCE CORRECTION: the browser ledger and web-style citation identifiers were unsupported and are withdrawn in full; no later browser corroboration is claimed. The actual functions.web_extract attempt failed because the configured backend cannot extract URLs. Source evidence rests exclusively on inspected immutable primary XML/HTML/PDF, actual direct-HTTP retrieval receipts and inherited source receipts. Scientific conclusions and RNA values are unchanged. No inherited scientific code was executed; no application/harness/skills were changed.

The bounded task is complete as an evidence-backed non-identifiability result. Additional expression signatures cannot identify the missing selective rescue/activity/initiation contrast. EGR2 protein persistence remains a credible branch; its predominance over RNA regulation or parallel signaling is not established.
