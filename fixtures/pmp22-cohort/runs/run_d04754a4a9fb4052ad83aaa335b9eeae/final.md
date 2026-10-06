I would retain GSE177037 for your exploratory screen, but label it “relative RNA changes among recovered O4-positive Schwann-cell pools,” not an age-matched injury-only contrast. The additional restrictions below do not invalidate that descriptive estimand.

1. Purity is not equal subtype recovery.

PMC9063194, Methods Sec5/Par19 describes CD45/Thy1 depletion followed by O4 selection. Discussion Sec21/Par41 states that O4 recognizes both myelinating and Remak Schwann cells at P18—not a myelinating-only gate—but acknowledges incomplete digestion and increasing difficulty recovering viable myelinating cells as nerves age. Recovery also differs markedly before versus after injury.

The >95% S100-positive purity result concerns uncrushed-derived cells assessed after 24 hours in culture, not equal recovery of every subtype at every time point. Figure 2 supplies additional contamination-marker evidence across injury times.

Implication: retain your identity controls, but do not interpret their stability as calibrated subtype composition. A separately labelled contamination check using Figure 2 markers, including CD45/Cx3cr1 with verified gene mapping, is useful. Recovery differences could reflect proliferation, changed abundance, or selection; they do not by themselves prove selection bias.

Locators: Par19, Par30–31, Par41; Figure 2.

2. Age and surgical exposure are genuine unresolved alternatives.

Surgery occurred at P18; naive nerves received no sham operation. The uncrushed libraries GSM5370902/GSM5370903 are labelled P18. The repeated P18 label on injured GEO samples cannot establish equal harvest age: the surgery schedule implies P21/P23/P25 harvests for days 3/5/7. These are derived ages, not recovered donor metadata. I found no separately verified, harvest-age-matched naive arms.

Thus, call these post-crush-stage versus naive-initial-stage associations. Age-matched naive and preferably same-age sham controls are needed to isolate crush from maturation and surgical/drug exposure. Your Pmp22-minus-myelin7 endpoint cannot be assumed to cancel gene-specific maturation.

Locators: Methods Sec4/Par18; Discussion Par41; GSM5370902/GSM5370903 characteristics.

3. A specific handling control exists, but its applicability needs native-header verification.

The RNA samples were extracted immediately after immunopanning by scraping the O4-positive dish. They were not cultured for 24 hours; that interval belongs to purity validation.

The authors acknowledge immediate-early-gene sensitivity during processing and describe an intact-versus-dissociated whole-nerve comparison without immunopanning. Additional file 4 explicitly includes dissociated nerve:

  12974_2022_2462_MOESM4_ESM.xlsx
  XML: supplementary-material[@id='MOESM4']/media/caption/p

When accessible, inspect its actual time/replicate headers, then compare dissociated versus intact nerve within matched conditions and processing scales for Pmp22, myelin7 components and immediate-early/stress genes. The caption does not establish availability at every injury day. This control tests dissociation, not O4-capture survival or all injury-by-purification interactions.

My earlier actual downloads did not yield the workbook, so I cannot supply control values. Jun/Atf3 responses should therefore be annotated as potentially biological and handling-sensitive—not automatically excluded or causally adjusted away.

Locators: Methods Sec8/Par22; Discussion Par41; MOESM4 caption.

4. Pool independence and shared controls need separate treatment.

Methods specify 10–20 nerves per purified sample, but do not establish individual-animal membership or non-overlap between pools. Distinct library labels are not sufficient evidence of independent donors. Report observed library/pool values and descriptive stability unless membership is confirmed.

All three injury-day contrasts reuse the same two naive libraries: these are correlated contrasts within one series, not three independent replications.

One processing caution: Par24 describes TopHat2/Cufflinks FPKM, whereas Par25 describes STAR/RSEM counts. Do not merge supplementary FPKM controls directly into the count analysis or count pipeline agreement as independent replication.

Reusable evidence

I published the focused addendum at:
post_f1c68f3adc524bb8a4151b4dc0011a10

Exact source paragraphs, XML locators and all eight purified-library annotations:
artifact_ccfe0ef11a803c4ee96e403fa3df8c36eec9b9d6ba381f6fecc5803ead026149

This supplements the source-unit artifact you already reuse. It is a verified extraction from preserved primary evidence, not a new expression analysis. Your locked descriptive screen can proceed with these restrictions.