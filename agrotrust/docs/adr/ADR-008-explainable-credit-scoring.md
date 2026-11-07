# ADR-008: Rule-based explainable credit scoring as the baseline, ML as an addition

**Status:** Accepted

## Context
Spec sections 19-20 require both a transparent baseline score and room for an ML-based signal,
with an explicit requirement that credit decisions be explainable and free of unsupported/
discriminatory assumptions.

## Decision
`modules/lending/scoring.py` is the *only* thing that gates a loan approval decision
(`LendingService.decide()` checks `credit_assessments.score` against the product's
`min_credit_score`). It is a fully named, additive point system (base score, +verified farm,
+KYC, +marketplace track record, +on-time repayment history, -late repayments, -prior defaults)
with every factor and its point contribution stored in `credit_assessments.factors` (JSON) -
an applicant can always be told exactly why they scored what they did.

`modules/ml/service.py`'s yield-prediction model (scikit-learn `LinearRegression`, falling back
to a documented naive average when there isn't enough historical data to fit a real model) is
kept entirely separate and is not wired into the lending decision at all in this build - it
answers a different question (expected harvest volume) that could inform loan sizing in a
future iteration, but only as an additional, separately-labelled signal, never as a replacement
for the explainable baseline.

## Consequences
- A rejected applicant's `decision_reason` plus their `credit_assessments.factors` gives a
  complete, human-readable account of the decision - no black-box score to defend or explain
  in a dispute or regulatory review.
- If an ML credit signal is added later, it must be stored as its own labelled
  `ml_predictions` row (as the yield model already demonstrates the pattern for) and surfaced
  to the decision-maker *alongside* the rule-based score, not merged into it silently.
