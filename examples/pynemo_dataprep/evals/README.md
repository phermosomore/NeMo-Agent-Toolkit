# Evaluation System for PhysicsNemo Agent

This directory contains a simple evaluation system for running test questions through the PhysicsNemo NeMo Agent Toolkit agent.

## Files

- `questions.txt` - Contains evaluation questions (one per paragraph, separated by blank lines)
- `run_eval.sh` - Bash script that runs all questions and saves results
- `list_runs.sh` - Lists all available evaluation runs with statistics
- `summarize_results.sh` - Shows summary statistics for a specific run
- `compare_runs.sh` - Compares results between two evaluation runs
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
# Run with auto-generated timestamp name
./examples/pynemo_dataprep/evals/run_eval.sh

# Run with custom name
./examples/pynemo_dataprep/evals/run_eval.sh baseline
./examples/pynemo_dataprep/evals/run_eval.sh experiment_v2
./examples/pynemo_dataprep/evals/run_eval.sh temperature_0.7
```

Or from the evals directory:

```bash
cd examples/pynemo_dataprep/evals
./run_eval.sh my_run_name
```

### Run a Single Question

To test a single question manually:

```bash
nat run --config_file=examples/pynemo_dataprep/configs/config.yaml \
  --input "Your question here"
```

## Results

Each evaluation run creates a directory under `results/` with the run name:

```
results/
├── baseline/
│   ├── question_1.txt
│   ├── question_2.txt
│   ├── ...
│   └── run_summary.txt
├── experiment_v2/
│   ├── question_1.txt
│   ├── question_2.txt
│   ├── ...
│   └── run_summary.txt
└── run_20250122_143055/
    ├── question_1.txt
    ├── ...
    └── run_summary.txt
```

Each result file contains:
- The original question
- The full agent response and trace
- Timestamp of completion
- Any error messages (if the command failed)

The `run_summary.txt` file contains:
- Run metadata (name, date, config)
- Success/failure status for each question
- Quick overview of the run

## Viewing Results

```bash
# List all evaluation runs with statistics
./evals/list_runs.sh

# Or view directory structure
ls -lh evals/results/

# View summary of the most recent run
./evals/summarize_results.sh

# View summary of a specific run
./evals/summarize_results.sh baseline

# View a specific result
cat evals/results/baseline/question_1.txt

# View the first 50 lines of each result in a run
head -50 evals/results/baseline/*.txt

# Search for specific content across all results in a run
grep -i "error" evals/results/baseline/*.txt

# Search across ALL runs
grep -i "error" evals/results/*/*.txt
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

To remove specific run:

```bash
rm -rf evals/results/baseline
```

To remove all results:

```bash
rm -rf evals/results/*/
```

### Compare Multiple Runs

```bash
# Run baseline evaluation
./evals/run_eval.sh baseline

# Run with different configuration
# (edit config.yaml to change parameters like temperature)
./evals/run_eval.sh experiment_high_temp

# View individual summaries
./evals/summarize_results.sh baseline
./evals/summarize_results.sh experiment_high_temp

# Compare runs side-by-side
./evals/compare_runs.sh baseline experiment_high_temp
```

The comparison script shows:
- Success/failure rates for each run
- Question-by-question comparison
- Visual indicators showing which run performed better
- File size comparisons
- Timestamps and metadata

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

## Example Workflows

### A/B Testing Different Configurations

```bash
# Test baseline configuration
./evals/run_eval.sh baseline

# Modify config.yaml (e.g., change temperature from 0.7 to 0.3)
# Then run with new name
./evals/run_eval.sh low_temperature

# Compare results
./evals/compare_runs.sh baseline low_temperature
```

### Testing Different Model Versions

```bash
# Test with model v1
./evals/run_eval.sh model_llama3_8b

# Update config to use different model
./evals/run_eval.sh model_llama3_70b

# Compare performance
./evals/compare_runs.sh model_llama3_8b model_llama3_70b
```

### Daily/Weekly Regression Testing

```bash
# Run with timestamp (automatic naming)
./evals/run_eval.sh

# Or use descriptive names with dates
./evals/run_eval.sh regression_2025_01_22
```

## Quick Reference

### All Available Commands

```bash
# Run evaluations
./run_eval.sh                    # Auto-generated timestamp name
./run_eval.sh my_run_name        # Custom run name

# View and manage runs
./list_runs.sh                   # List all runs with statistics
./summarize_results.sh           # Summarize most recent run
./summarize_results.sh baseline  # Summarize specific run

# Compare runs
./compare_runs.sh run1 run2      # Side-by-side comparison

# View individual results
cat results/baseline/question_1.txt
cat results/baseline/run_summary.txt

# Search across results
grep -i "keyword" results/baseline/*.txt
grep -i "error" results/*/*.txt

# Clean up
rm -rf results/old_run_name      # Delete specific run
rm -rf results/*/                # Delete all runs
```

## Future Enhancements

Consider adding:
- Ground truth answers for automated evaluation scoring
- Integration with `nat eval` for metrics (BLEU, semantic similarity, etc.)
- Parallel execution for faster processing
- JSON output format for programmatic analysis
- Cost tracking (token usage, API costs)
- Response time measurements





