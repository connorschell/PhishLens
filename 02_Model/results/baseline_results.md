# WBS 2.1 - baseline results

Generated 2026-11-24T17:03:21+00:00. Test split: 4087 held-out messages, campaign-aware, measured leakage 0%.

Accuracy is not reported. The test split is 53.7% phishing and an inbox is not.

## Full feature set vs ablated

The ablated run removes the six features whose single-feature AUC in WBS 1.5 suggested they were separating the 2002 ham corpus from the 2022+ phishing corpus rather than separating phishing from legitimate mail: `has_http_only_link`, `link_density_per_100_words`, `max_url_length`, `subject_has_reply_prefix`, `subject_length`, `subject_nonascii`.

| Metric | Full (43 features) | Ablated (37 features) |
|---|---|---|
| Precision | 0.7547 | 0.7308 |
| Recall | 0.8387 | 0.6904 |
| False-positive rate, ham | 0.1224 | 0.105 |
| False-positive rate, spam | 0.2423 | 0.2869 |
| False-positive rate, overall | 0.1383 | 0.1291 |
| ROC AUC | 0.9311 | 0.8824 |
| PR AUC | 0.8854 | 0.8119 |

The two runs above sit at each variant's own tier thresholds, which differ. The table below removes that difference by holding the false-positive rate on ordinary correspondence equal and comparing what each model catches at that cost - the comparison that actually matters, since a user picks a tolerance, not a threshold.

| Matched operating point | Full | Ablated |
|---|---|---|
| Recall at 1% ham FPR | 0.3975 (P 0.9681) | 0.367 (P 0.9335) |
| Recall at 5% ham FPR | 0.6722 (P 0.8702) | 0.5334 (P 0.811) |
| Recall at 10% ham FPR | 0.8205 (P 0.7797) | 0.6352 (P 0.7457) |

## Reference ceiling

A gradient-boosted tree ensemble trained on the same features, evaluated only to measure what explainability costs. It is not shipped: it offers no exact per-feature contribution, which WBS 2.2 and 2.3 require.

| Variant | Logistic PR AUC | GBM PR AUC |
|---|---|---|
| Full | 0.8854 | 0.9886 |
| Ablated | 0.8119 | 0.967 |

## Severity tiers

Thresholds are set on out-of-fold training predictions against a false-positive budget on ordinary correspondence, not on round numbers: dangerous <= 0.5% ham FPR, suspicious <= 2.0% ham FPR, caution <= 10.0% ham FPR.

| Tier | Threshold | Test messages | % actually phishing |
|---|---|---|---|
| clear | - | 2558 | 8.7 |
| caution | 0.579 | 550 | 52.9 |
| suspicious | 0.829 | 367 | 74.7 |
| dangerous | 0.938 | 612 | 96.2 |

## Strongest learned weights (full model)

| Feature | Standardised weight |
|---|---|
| `link_domain_matches_sender` | -2.015 |
| `max_url_length` | 1.283 |
| `subject_length` | 1.249 |
| `link_count` | -1.153 |
| `no_link_matches_sender_domain` | -1.09 |
| `link_density_per_100_words` | -0.953 |
| `sender_display_nonascii` | 0.741 |
| `has_url_shortener` | 0.692 |
| `subject_has_reply_prefix` | -0.689 |
| `brand_claimed_but_sender_unrelated` | 0.489 |
| `has_http_only_link` | -0.448 |
| `body_word_count` | -0.41 |
