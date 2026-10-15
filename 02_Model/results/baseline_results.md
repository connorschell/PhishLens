# WBS 2.1 - baseline results

Generated 2026-10-15T18:52:08+00:00. Test split: 2546 held-out messages, campaign-aware, measured leakage 0%.

Accuracy is not reported. The test split is 53.7% phishing and an inbox is not.

## Full feature set vs ablated

The ablated run removes the six features whose single-feature AUC in WBS 1.5 suggested they were separating the 2002 ham corpus from the 2022+ phishing corpus rather than separating phishing from legitimate mail: `has_http_only_link`, `link_density_per_100_words`, `max_url_length`, `subject_has_reply_prefix`, `subject_length`, `subject_nonascii`.

| Metric | Full (43 features) | Ablated (37 features) |
|---|---|---|
| Precision | 0.8819 | 0.8673 |
| Recall | 0.9561 | 0.7505 |
| False-positive rate, ham | 0.1186 | 0.0941 |
| False-positive rate, spam | 0.2161 | 0.2216 |
| False-positive rate, overall | 0.1484 | 0.1332 |
| ROC AUC | 0.9781 | 0.8836 |
| PR AUC | 0.9832 | 0.9038 |

The two runs above sit at each variant's own tier thresholds, which differ. The table below removes that difference by holding the false-positive rate on ordinary correspondence equal and comparing what each model catches at that cost - the comparison that actually matters, since a user picks a tolerance, not a threshold.

| Matched operating point | Full | Ablated |
|---|---|---|
| Recall at 1% ham FPR | 0.8471 (P 0.9822) | 0.3058 (P 0.9721) |
| Recall at 5% ham FPR | 0.9217 (P 0.9481) | 0.5889 (P 0.9221) |
| Recall at 10% ham FPR | 0.9488 (P 0.9032) | 0.7213 (P 0.8772) |

## Reference ceiling

A gradient-boosted tree ensemble trained on the same features, evaluated only to measure what explainability costs. It is not shipped: it offers no exact per-feature contribution, which WBS 2.2 and 2.3 require.

| Variant | Logistic PR AUC | GBM PR AUC |
|---|---|---|
| Full | 0.9832 | 0.9968 |
| Ablated | 0.9038 | 0.9757 |

## Severity tiers

Thresholds are set on out-of-fold training predictions against a false-positive budget on ordinary correspondence, not on round numbers: dangerous <= 0.5% ham FPR, suspicious <= 2.0% ham FPR, caution <= 10.0% ham FPR.

| Tier | Threshold | Test messages | % actually phishing |
|---|---|---|---|
| clear | - | 1064 | 5.6 |
| caution | 0.298 | 274 | 46.4 |
| suspicious | 0.741 | 110 | 85.5 |
| dangerous | 0.888 | 1098 | 98.9 |

## Strongest learned weights (full model)

| Feature | Standardised weight |
|---|---|
| `max_url_length` | 4.304 |
| `no_link_matches_sender_domain` | -2.621 |
| `link_domain_matches_sender` | -2.152 |
| `has_http_only_link` | -2.148 |
| `distinct_link_domain_count` | -1.28 |
| `subject_nonascii` | 1.267 |
| `has_url_shortener` | 1.146 |
| `subject_has_reply_prefix` | -0.829 |
| `sender_display_nonascii` | 0.789 |
| `max_subdomain_depth` | -0.671 |
| `sender_domain_digit_count` | 0.61 |
| `link_count` | 0.608 |
