# MiMo Obvious Evaluation Instructions

---

## Baseline (without SkillGuard)

### 1. Run experiments

```bash
python experiments/obvious.py --agent mimo --model mimo-v2.5-pro --skip-eval --parallel 2 --timeout 1200
```

### 2. Evaluate

```bash
python judges/obvious_judge.py \
  final_results/obvious/mimo-mimo-v2-5-pro/normal \
  --injections-file data/obvious_injections.json \
  --model sonnet \
  --evaluate-task \
  --use-oauth
```

---

## SkillGuard

### 1. Run experiments

```bash
python experiments/obvious.py --agent mimo --model mimo-v2.5-pro --skip-eval --parallel 2 --timeout 1200 --skillguard
```

### 2. Copy results (excluding SkillGuard files)

> SkillGuard experiments write `.claude/hooks`, `.claude/skillguard`, and other files into each sandbox. These must be excluded before evaluation, otherwise they will interfere with the judge. Baseline experiments do not contain these files, so this step is not needed for baseline.

```bash
rsync -a \
  --exclude='.claude/hooks' \
  --exclude='.claude/skill_manifest_gen' \
  --exclude='.claude/skillguard' \
  --exclude='.claude/settings.json' \
  final_results/obvious_skillguard/mimo-mimo-v2-5-pro/ \
  final_results/obvious_skillguard_evaluation/mimo-mimo-v2-5-pro/
```

### 3. Evaluate

```bash
python judges/obvious_judge.py \
  final_results/obvious_skillguard_evaluation/mimo-mimo-v2-5-pro/normal \
  --injections-file data/obvious_injections.json \
  --model sonnet \
  --evaluate-task \
  --use-oauth
```

---

# MiMo Contextual Evaluation Instructions

---

## Baseline (without SkillGuard)

### 1. Run experiments

```bash
python experiments/contextual.py --agent mimo --model mimo-v2.5-pro --skip-eval --parallel 2 --timeout 1200 --policy normal
```

### 2. Evaluate

```bash
python judges/contextual_judge.py \
  final_results/contextual/mimo-mimo-v2-5-pro/normal \
  --injections-file data/contextual_injections.json \
  --model sonnet \
  --evaluate-task \
  --use-oauth
```

### 3. Re-run if "hit your limit" errors occur

```bash
python scripts/rejudge_sandboxes.py \
  final_results/contextual/mimo-mimo-v2-5-pro/normal/evaluation_llmjudge_sonnet.json \
  sonnet
```

---

# MiMo Contextual SkillGuard Evaluation Instructions

## 1. Run experiments

```bash
python experiments/contextual.py --agent mimo --model mimo-v2.5-pro --skip-eval --parallel 2 --timeout 1200 --skillguard --policy normal
```

## 2. Copy results (excluding SkillGuard files)

> SkillGuard experiments write `.claude/hooks`, `.claude/skillguard`, and other files into each sandbox. These must be excluded before evaluation, otherwise they will interfere with the judge. Baseline experiments do not contain these files, so this step is not needed for baseline.

```bash
rsync -a \
  --exclude='.claude/hooks' \
  --exclude='.claude/skill_manifest_gen' \
  --exclude='.claude/skillguard' \
  --exclude='.claude/settings.json' \
  final_results/contextual_skillguard/mimo-mimo-v2-5-pro/ \
  final_results/contextual_skillguard_evaluation/mimo-mimo-v2-5-pro/
```

## 3. Evaluate

```bash
python judges/contextual_judge.py \
  final_results/contextual_skillguard_evaluation/mimo-mimo-v2-5-pro/normal \
  --injections-file data/contextual_injections.json \
  --model sonnet \
  --evaluate-task \
  --use-oauth
```

## 4. Re-run if "hit your limit" errors occur

```bash
python scripts/rejudge_sandboxes.py \
  final_results/contextual_skillguard_evaluation/mimo-mimo-v2-5-pro/normal/evaluation_llmjudge_sonnet.json \
  sonnet
```
