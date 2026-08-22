# LearnLM Section 3.4 Analysis Simulation

This folder contains two learning aids for Section 3.4 of `LearnLM: Improving Gemini for Learning`.

The recommended version is the data-first, stage-based pipeline experience:

```text
docs/paper/google_learnLM/Analysis_3.4_simulation/pipeline.html
```

Open `pipeline.html` in a browser. It does not require a server or Python dependencies.

## Stage-Based Pipeline

The stage-based version lets you play the role of a researcher and move through the analysis workflow:

1. Inspect the evaluation data.
2. Compare naive model averages.
3. Identify repeated-measurement problems.
4. Estimate adjusted model effects.
5. Add uncertainty intervals.
6. Code open-ended feedback into qualitative themes.

The page first presents the simulated dataset, its fields, and repeated-measurement clues. After inspecting the data, use the guided stages below it. Each stage asks you to make a small analysis decision before unlocking the next stage.

## Streamlit Dashboard

The Streamlit app is a dashboard-style simulation of the same ideas.

It helps you explore three ideas:

- Why repeated evaluator/scenario measurements make raw averages incomplete.
- How a hierarchical-analysis intuition separates model effect, evaluator bias, scenario difficulty, and random noise.
- How open-ended feedback can be coded into qualitative themes.

### Run Streamlit

From the repository root:

```bash
python3 -m venv docs/paper/google_learnLM/Analysis_3.4_simulation/.venv
docs/paper/google_learnLM/Analysis_3.4_simulation/.venv/bin/pip install -r docs/paper/google_learnLM/Analysis_3.4_simulation/requirements.txt
docs/paper/google_learnLM/Analysis_3.4_simulation/.venv/bin/streamlit run docs/paper/google_learnLM/Analysis_3.4_simulation/app.py
```

If you already have Streamlit installed, you can run:

```bash
streamlit run docs/paper/google_learnLM/Analysis_3.4_simulation/app.py
```

## What Is Simulated

The app creates rows like:

```text
evaluator_id, scenario_id, model, score, feedback theme flags
```

The quantitative section compares:

- `Naive Average`: direct mean score by model.
- `Adjusted Model Effect`: a simplified correction for evaluator strictness and scenario difficulty.
- `Uncertainty`: bootstrap intervals as an intuitive stand-in for the paper's Bayesian credible intervals.

The qualitative section summarizes simulated codebook themes such as:

- `gives_away_answers`
- `keeps_on_topic`
- `is_engaging`
- `challenges_learner`
- `step_by_step`
- `clarity`

This is not a reproduction of the paper's real statistical model. It is a teaching tool for making the analysis logic easier to see.
