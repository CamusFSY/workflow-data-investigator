# Intent resolution in data analysis agents

## Research status and scope

This research summary accompanies Workflow Data Investigator. It describes an exploratory clarification pilot completed before the repository's later engineering evaluations. The associated manuscript is a research draft; no conference acceptance or peer-review claim is made here.

The research question is narrow: when a request admits two valid metric definitions, does an agent obtain authoritative evidence of the intended definition before presenting a single resolved answer? The pilot separates that question from SQL execution, numerical accuracy, and the factual support of the final explanation.

The connection to the product is methodological. It motivates recording which evidence resolves a metric definition and checking numerical results separately from narrative claims. The pilot is not an evaluation of the current software release, and its episode counts must not be combined with later product tests or live evaluations.

## The two task families

The pilot contains 64 episodes from two synthetic families, with two policy conditions, two data-world variants, two catalog orders, two intended definitions, and two repeats. These are repeated variants of two task structures, not 64 independent real-world tasks.

- Conversion, P1: definition A counts sessions with at least one paid order divided by all sessions in the month; definition B counts purchasing visitors divided by visitors with a session in the month.
- Sales, P4: definition A attributes order value to acceptance month; definition B attributes it to fulfillment month.

The conditions are labeled FREE and ASK. Both could use clarification, and FREE did so in most episodes. The comparison must not be described as an agent with access to clarification versus one without it.

## What was observed

| Recorded outcome | ASK | FREE |
| --- | ---: | ---: |
| Episodes | 32 | 32 |
| Actual authoritative clarification received | 32 | 30 |
| Intended definition resolved and matched | 32 | 30 |
| Unresolved conditional final answers | 0 | 2 |
| Unsupported intent commitments under the recorded endpoint | 0 | 0 |
| Model requests | 139 | 130 |
| Historical estimated model cost, CNY | 0.470136 | 0.460396 |

ASK resolved the intended definition in 32/32 episodes. FREE resolved it in 30/32 and returned conditional answers covering both definitions in the remaining two. The observed resolution difference is two episodes, or 6.25 percentage points. Those two conditional answers were appropriately unresolved under the intent endpoint; they are not two demonstrated factual failures. Both occurred in the conversion family. Both conditions resolved all 16 sales episodes.

One ASK episode retains an unresolved coding distinction between a conditional and an unconditional answer because of a payment-status qualification. Its definition commitment, intent match, and resolution codes remain unchanged. Thus 32 resolved ASK episodes must not be relabeled as 32 unambiguously unconditional answers.

The zero unsupported-intent result concerns whether an eligible resolved-intent assertion occurred before authoritative clarification. It does not establish that every SQL query, number, explanation, or user-facing statement was correct. Descriptive review separately identified unsupported cross-period identity or order-cohort explanations and one calculation/composition inconsistency. Those observations were collected after execution and are not a comprehensive numerical-accuracy endpoint or a new error-rate benchmark.

The 269 recorded model requests total 324,490 input tokens and 35,194 output tokens. The historical estimate of CNY 0.930532 uses CNY 2 per million input tokens and CNY 8 per million output tokens. It is a historical accounting estimate, not a current price quote, provider invoice, or full research-lifecycle cost.

## Evidence and interpretation limits

- The scope is two synthetic task families. Repeats and presentation variants do not establish cross-domain generalization or deployment reliability.
- The host allowed eight model requests while the prompt described four. This HOST8/PROMPT4 discrepancy is retained as an experimental limitation; the study must not be described as a clean four-call or uniformly communicated eight-call comparison.
- Forty-seven episodes lack a definitive per-message delivery flag for an earlier assistant statement. The recorded adjudication considered both delivery interpretations. In each case the relevant statement, if delivered, was after the authoritative reply, so the unsupported-intent endpoint remains unchanged. The delivery fact itself remains unknown.
- The operational coding handoff was sealed after execution and before coding, drawing on existing rules. The missing-delivery and payment-status interpretations include post-execution handling. These must not be presented as newly preregistered before the runs.
- The review records describe multiple coders and adjudication, but this summary does not establish a human-only annotation study or independent expert validation.
- The two-episode descriptive difference does not establish an accuracy advantage, a safety advantage, an optimal clarification policy, statistical superiority, or a novel algorithm.
- This summary is not a complete reproducibility package. The original prompts, model/version configuration, full run traces, and complete coding provenance are required to reproduce or independently regrade the study.

## A bounded conceptual observation

Suppose the evidence visible to an agent is compatible with two possible user intentions that require different requested metric definitions. A single unconditional definition choice cannot be guaranteed correct for both intentions without additional distinguishing evidence. Reporting the alternatives conditionally can preserve uncertainty; an authoritative clarification can resolve it if the reply is clear and correctly used.

This is an elementary identifiability observation, not a new theorem or a proof that the implemented agent is reliable. Receiving clarification also does not prove that subsequent calculations or explanations are correct. Likewise, equal monthly visitor counts do not establish that the visitors are the same people across months; that claim requires linking evidence.

## Related work and the limited contribution

Ambiguous database questions and clarification are established research topics. [AmbiQT](https://aclanthology.org/2023.emnlp-main.436/) studies questions admitting multiple SQL interpretations. [PRACTIQ](https://aclanthology.org/2025.naacl-long.13/) includes conversational clarification and, for some queries, helpful answers that cover multiple interpretations. [CLARITY](https://aclanthology.org/2026.acl-industry.86/) studies interactive ambiguity and incomplete clarification in NL2SQL systems.

The limited contribution of this pilot is a small, auditable case study that distinguishes received intent evidence, intent resolution, and other answer defects, while retaining conditional answers, coding ambiguity, execution issues, and accounting limitations. It does not reproduce those prior systems or compare against their reported benchmark scores.

Further work would need a prospectively frozen protocol, consistent budgets, exact delivery logging, stronger matched baselines, independently constructed task families, and separate supported-accuracy and resolution measurements. No such future result is implied by this summary.
