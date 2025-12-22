# Evaluation System for PhysicsNemo Agent

This directory contains a simple evaluation system for running test questions through the PhysicsNemo NeMo Agent Toolkit agent.

## Files

- `questions.txt` - Contains evaluation questions (one per paragraph, separated by blank lines)
- `run_eval.sh` - Bash script that runs all questions and saves results
- `results/` - Directory where evaluation results are saved (created automatically)

## Question Format

Questions in `questions.txt` should be separated by **blank lines**. This allows multi-line questions (such as code examples). For example:

```
What is PhysicsNemo?

Can you run this code example:
>>> import torch
>>> from physicsnemo.models import Model
>>> model = Model()

What are the supported architectures?
```

## Usage

### Run All Evaluations

From the repository root:

```bash
# Run all questions
./examples/pynemo_dataprep/evals/run_eval.sh
```

Or from the evals directory:

```bash
cd examples/pynemo_dataprep/evals
./run_eval.sh
```

### Run a Single Question

To test a single question manually:

```bash
nat run --config_file=examples/pynemo_dataprep/configs/config.yaml \
  --input "Your question here"
```

## Results

Each question generates a separate result file in `results/`:
- `question_1.txt`
- `question_2.txt`
- `question_3.txt`
- etc.

Each result file contains:
- The original question
- The full agent response and trace
- Timestamp of completion
- Any error messages (if the command failed)

## Viewing Results

```bash
# List all result files
ls -lh evals/results/

# View a specific result
cat evals/results/question_1.txt

# View the first 50 lines of each result
head -50 evals/results/*.txt

# Search for specific content across all results
grep -i "error" evals/results/*.txt
```

## Customization

### Modify Configuration

Edit the script variables at the top of `run_eval.sh`:

```bash
CONFIG_FILE="examples/pynemo_dataprep/configs/config.yaml"  # Change config file
QUESTIONS_FILE="${SCRIPT_DIR}/questions.txt"                # Change questions file
RESULTS_DIR="${SCRIPT_DIR}/results"                         # Change output directory
```

### Add More Questions

Simply add more questions to `questions.txt`, making sure to separate them with blank lines.

### Clean Results

To start fresh:

```bash
rm -rf evals/results/*
```

## Requirements

- NeMo Agent Toolkit installed and configured
- Valid configuration file at `examples/pynemo_dataprep/configs/config.yaml`
- Required environment variables set (e.g., `NVIDIA_API_KEY`)
- Milvus database populated with PhysicsNemo documentation (if using RAG)

## Troubleshooting

**Script fails with "command not found":**
- Make sure the script is executable: `chmod +x run_eval.sh`
- Ensure you're running from the correct directory

**Questions fail with errors:**
- Check that the config file path is correct
- Verify environment variables are set
- Ensure Milvus or other services are running if required

**Results directory not created:**
- The script will create it automatically
- Check file permissions in the evals directory

## Future Enhancements

Consider adding:
- Ground truth answers for evaluation scoring
- Automated evaluation metrics (e.g., using `nat eval`)
- Parallel execution for faster processing
- JSON output format for programmatic analysis
- Summary statistics across all questions

