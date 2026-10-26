# User guide for biologists

This guide is for biologists who want to use this framework to build a mechanistic
model of their own system. You do not need to be a programmer. You describe your
biology, review what the system proposes, and make the scientific decisions. The
framework does the modelling work, keeps a written record of everything, and stops
whenever a choice needs your judgement.

Installation is covered in the [README](../README.md#quick-start-claude-code). This
guide assumes Claude Code is installed and set up for this repository.

## What the framework can do for you

You start with a biological question, for example *"Why do cells carrying mutation X
stop responding to drug Y, and which combination might restore the response?"* The
framework helps you build a model in stages.

| Stage | What you get | Tool behind it |
|---|---|---|
| **Specification** | A written statement of your question, scope, key molecules, readouts and the results the model must reproduce | — |
| **Signalling network** | A network of interactions between your molecules, built from curated databases such as SIGNOR or OmniPath, with a record of how it was assembled | NeKo |
| **Literature evidence** | One report per interaction, checked against PubMed for existence, direction (activation or inhibition) and context | PubMed |
| **Boolean dynamics** | A model in which each molecule is ON or OFF. You can simulate wild type, knockouts, constitutive activation and drug-like perturbations, and compare their outcomes | MaBoSS |
| **Mechanistic ODEs** (optional) | A model with continuous concentrations and reaction rates, for questions that need quantities rather than ON/OFF states | BioMASS |
| **Multicellular configuration** | A tissue-level simulation set-up in which cells use the Boolean model to decide behaviours such as proliferation or death | PhysiCell / PhysiBoSS |

What it will **not** do:

- **It will not invent biology.** It never makes up interactions, parameter values,
  units or references. When something is unknown, it says so and asks you.
- **It will not treat a running simulation as proof.** A model that runs, or even
  reproduces a result, is a hypothesis consistent with that result. It is not
  validated biology.
- **It does not run tissue simulations.** It prepares PhysiCell configuration files
  for an existing PhysiCell installation.
- **ODEs have limits.** It does not calibrate ODE parameters to data, run
  sensitivity analyses, or couple ODE models to PhysiCell.

## How a working session goes

You talk to one assistant in Claude Code, the **orchestrator**. It plans the work
with you and sends each technical task to a **specialist**: the network curator,
literature reviewer, Boolean modeller, multicellular configurator or ODE modeller.
Each specialist can only touch its own tool. The orchestrator itself cannot change
any model directly; it delegates, reads the results back, and explains them to you.

A typical exchange looks like this:

1. You describe your goal or answer a question.
2. The orchestrator proposes the next step and lists the choices that need you.
3. You decide.
4. A specialist does the work and returns a summary with the exact files it produced.
5. The orchestrator checks the result, records it, and tells you what it found and
   what decision comes next.

Exploring and inspecting are done freely. Anything that changes the model or moves to
the next stage waits for your explicit approval, which is recorded in your own words.

## The decisions you will be asked to make

| Stage | Typical decisions |
|---|---|
| Specification | The question and its boundaries; which molecules, cell type and conditions are in scope; which experimental results the model must reproduce |
| Network | Which database to use; how far to search for connecting molecules; whether to keep only signed (activating or inhibiting) interactions; which interactions to keep, remove, or add from the literature |
| Evidence | How to act on a contested or unsupported interaction: keep it, remove it, or flag it as an assumption |
| Boolean dynamics | Which molecules are outputs; the initial state (what is ON at the start); which mutations or drug perturbations to simulate; summary readout nodes, such as "proliferation" or "apoptosis", and their rules |
| Numbers | Any parameter value or unit. Proposed numbers are always labelled as hypotheses until you approve them |
| Each transition | Whether the stage is ready to hand over to the next one, after two independent reviews |

**What an approval means.** An approval is tied to the exact version of the network
or model you reviewed. If anything changes afterwards (an interaction, a rule, a
readout, a rate), the old approval no longer applies, and you are asked again. This
keeps every result traceable to the precise model that produced it.

**Adding an interaction the database does not contain.** If you know from the
literature that an interaction exists, it can be added as a *manual literature* edge.
It gets its own evidence report, with the supporting PubMed IDs, and your approval.
It is clearly labelled as manually added, so it is never confused with database
content.

## Bringing your data and papers

- **Inputs.** Put your source material in `inputs/`: papers (PDF), tables, lists of
  genes, experimental measurements. These files are preserved when you restart or
  restore a model.
- **Data dictionary.** The orchestrator records identifiers, units and provenance in
  `DATA_DICTIONARY.md`. Tell it the units of your measurements: it never guesses
  units.
- **Validation targets.** The results the model should reproduce become the
  validation plan, for example *"knocking out B prevents activation of C"* or
  *"under drug Y, proliferation turns OFF"*.
- **Privacy.** If your data or manuscript are unpublished, never push this
  repository to a public remote. The framework never pushes on its own.

## The files that record your project

Everything important is written to plain files in the repository, so you can read
them at any time and nothing depends on remembering a chat.

| File or folder | What it contains |
|---|---|
| `MODEL_SPEC.md` | The question, scope, molecules, mechanisms, model type, inputs, outputs and limitations |
| `ASSUMPTIONS.md` | Assumptions, with accepted and proposed ones kept separate |
| `DECISIONS.md` | Every decision with its rationale and your approval. Interaction changes cite their evidence reports and PubMed IDs |
| `CURRENT_STATE.md` | The current stage, the list of modelling sessions so far, warnings and the next action |
| `VALIDATION_PLAN.md` and `VALIDATION_CRITERIA.yaml` | What the model must reproduce, and the results of each check |
| `DATA_DICTIONARY.md` | Identifiers, units, sources and versions |
| `evidence/reports/` | One literature report per reviewed interaction |
| `runs/` | Files produced by each modelling session: networks, model files, simulation results, specialist reports |

Every interaction and rule in the final model is labelled by where it came from:
taken from a database, supported by dedicated literature review, added manually from
the literature, chosen to fit target dynamics, or a summary readout.

## Reading the results

**Evidence reports.** Each report starts with a verdict (*supported*, *contradicted*,
*context-dependent* or *insufficient evidence*), the interaction type and a
confidence level. It lists supporting studies with PubMed IDs and organism, cell type
and study type, then conflicting or context-specific evidence, excluded references
with reasons, and open questions for you. A report never overwrites an earlier
one.

**Simulations.** Each simulation run gets a **run ID** and is stored with everything
needed to reproduce it: the exact model, settings, initial state and mutations. The
orchestrator summarises each run (for example, which output nodes end up ON and with
what probability) and can show plots. Wild type and mutants are always compared under
matched settings.

**Validation.** Each target in your validation plan is checked against saved results.
Results are recorded as passed, failed, or incomplete when a check could not finish;
an incomplete check never counts as a pass. Even a full pass means the model is
consistent with those observations. It does not prove the mechanism.

## Checkpoints and trying alternatives

Work on a model branch, created once at the start, for example:

```text
git switch -c model/my-project
```

| Command (type it in Claude Code) | What it does |
|---|---|
| `/checkpoint-model` | Saves the current state as a local Git checkpoint, after checking the records |
| `/validate-stage` | Runs the two independent reviews (scientific review and reproducibility audit) before a stage transition |
| `/model-list` | Shows the current model and saved archives |
| `/model-archive <name>` | Saves the current direction under a name you choose |
| `/model-restart` | Saves an automatic recovery point, then starts again from empty templates |
| `/model-restore <name>` | Brings back a saved direction |

After a restart or restore, type `/clear` so the assistant starts fresh from the
files rather than from the previous conversation. Your `inputs/` are never removed by
these commands.

## Tips for a good collaboration

- **State the question and the evidence you trust.** Say which experiments matter
  most and which papers are your primary sources.
- **Name the readouts.** For example: "proliferation and apoptosis, as measured by
  Ki-67 and cleaved caspase-3".
- **Give units and values only when you have them.** If you do not know a number,
  say so; it will stay a labelled hypothesis.
- **Ask for the choices.** "What decisions do you need from me?" is always a good
  prompt.
- **Disagree freely.** You can reject a proposed interaction, rule or readout, and
  the reason is recorded.

### Example first conversation

> **You:** I study how EGFR inhibition affects apoptosis in lung adenocarcinoma cells.
> My key results are in `inputs/our_paper.pdf`. Help me write the specification and
> tell me which decisions you need from me.
>
> **Orchestrator:** proposes a scope (molecules, cell type, conditions) and a list of
> validation targets drawn from your paper, marks anything it is unsure of, and asks
> you to confirm the readouts, the database for the network, and which results are
> essential to reproduce.

## Frequently asked questions

**Something is labelled a "hypothesis". Is it wrong?**
No. It means the value or choice has no direct support yet and needs your approval
before it is used. Hypotheses stay labelled in the records.

**Why does it keep asking me to approve things again?**
An approval covers one exact version of the model. Any later change creates a new
version that needs a new approval.

**A specialist reported "blocked" or "failed". What now?**
The orchestrator explains why, for example a missing input or an unavailable
service. Nothing is silently retried or replaced; you decide how to proceed.

**Can I see exactly what was done?**
Yes. `DECISIONS.md` and `CURRENT_STATE.md` give the history, and `runs/` holds the
files and each specialist's report.

**Which tools does it use underneath, and where are the technical details?**
NeKo, MaBoSS, PhysiCell and BioMASS, through the `mcp-biomodelling-servers` package.
For technical details, see the [documentation map](README.md).
