# Spec Delta

## Purpose

Defines the plain-language explanation, likely root cause, and missing-documentation checklist of
a diagnosed case.

## ADDED Requirements

### Requirement: Explanation and root cause are shown
After classification, diagnosis SHALL send the case facts, the classification, the code notes,
and the payer's rule cards to the `explanation` role through the registered `explanation` prompt
template, and SHALL store a typed `Explanation` with a plain-language explanation and a likely root
cause on the case's diagnosis; the pane SHALL show both.

#### Scenario: Explanation and root cause are shown
- **WHEN** the explanation step runs on a diagnosed case
- **THEN** the case shows a plain-language explanation and a likely root cause

#### Scenario: The explanation model is missing
- **WHEN** the explanation model is unavailable after classification succeeded
- **THEN** the job ends failed with model_unavailable and the case keeps that run's classification

### Requirement: Checklist lists missing documentation
The checklist SHALL hold only documents listed on the matched payer's `required_docs` rule card,
in the card's order and wording, each with the model's reason when it gave one; when the reply
selects no valid item, every listed document SHALL be shown. A case whose payer matches no rule
card SHALL get an empty checklist, and the pane SHALL say that no rule card is on file. The
diagnosis SHALL name each rule card used with its source, verified-on date, and stale flag.

#### Scenario: Checklist lists missing documentation
- **WHEN** the explanation step runs on a diagnosed case whose payer has a rule card with required documents
- **THEN** the case shows a checklist of missing documentation items drawn from the rule card's required documents

#### Scenario: The model names a document that is not on the card
- **WHEN** the explanation reply selects item numbers outside the card's list
- **THEN** those entries are dropped and the checklist holds only the card's own documents

#### Scenario: No rule card for the payer
- **WHEN** the case's payer matches no rule card
- **THEN** the checklist is empty and the pane says no rule card is on file

### Requirement: Rule cards match the payer by the start of its name
A rule card SHALL apply to a case when its payer's words begin the case's payer name (ignoring
case, punctuation, and a leading "the"); the card payer with the most words SHALL win, and per
topic only the most recently verified card of that payer SHALL be used.

#### Scenario: A payer named inside another payer's name
- **WHEN** the case's payer is AETNA MEDICARE ADVANTAGE and only Medicare has rule cards
- **THEN** no rule card is used

#### Scenario: Two spellings of one payer
- **WHEN** the corpus holds required_docs cards for Aetna and for AETNA
- **THEN** the checklist comes from the more recently verified one and at most one card per topic is named
