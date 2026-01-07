#!/bin/bash

# List All Evaluation Runs
# Shows all available evaluation runs with metadata

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_BASE_DIR="${SCRIPT_DIR}/results"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}  Available Evaluation Runs${NC}"
echo -e "${BLUE}================================================${NC}"
echo ""

# Check if results directory exists
if [ ! -d "${RESULTS_BASE_DIR}" ]; then
    echo -e "${YELLOW}No results directory found${NC}"
    echo "Run ./run_eval.sh to create your first evaluation run"
    exit 0
fi

# Get all run directories
runs=($(ls -1t "${RESULTS_BASE_DIR}" 2>/dev/null | grep -v ".gitkeep"))

if [ ${#runs[@]} -eq 0 ]; then
    echo -e "${YELLOW}No evaluation runs found${NC}"
    echo ""
    echo "Run an evaluation with:"
    echo "  ./run_eval.sh [RUN_NAME]"
    exit 0
fi

echo "Total runs: ${#runs[@]}"
echo ""
echo "------------------------------------------------"
printf "%-30s %10s %8s %8s %s\n" "RUN NAME" "QUESTIONS" "SUCCESS" "FAILED" "DATE"
echo "------------------------------------------------"

for run in "${runs[@]}"; do
    run_dir="${RESULTS_BASE_DIR}/${run}"
    
    if [ ! -d "$run_dir" ]; then
        continue
    fi
    
    # Count questions
    total_questions=$(find "$run_dir" -name "question_*.txt" 2>/dev/null | wc -l | tr -d ' ')
    
    # Count errors
    error_count=$(grep -l "ERROR:" "$run_dir"/question_*.txt 2>/dev/null | wc -l | tr -d ' ')
    success_count=$((total_questions - error_count))
    
    # Get date
    run_date=""
    if [ -f "$run_dir/run_summary.txt" ]; then
        run_date=$(grep "^Date:" "$run_dir/run_summary.txt" 2>/dev/null | sed 's/Date: //' | cut -d' ' -f1-3)
    fi
    
    # Color code based on success rate
    if [ "$error_count" -eq 0 ] && [ "$total_questions" -gt 0 ]; then
        status_color="${GREEN}"
    elif [ "$error_count" -gt 0 ] && [ "$success_count" -gt 0 ]; then
        status_color="${YELLOW}"
    else
        status_color="${RED}"
    fi
    
    printf "${status_color}%-30s %10s %8s %8s${NC} %s\n" \
        "$run" "$total_questions" "$success_count" "$error_count" "$run_date"
done

echo "------------------------------------------------"
echo ""

# Show total disk usage
total_size=$(du -sh "${RESULTS_BASE_DIR}" 2>/dev/null | awk '{print $1}')
echo "Total disk usage: ${total_size}"
echo ""

echo "Commands:"
echo "  View summary:        ./summarize_results.sh [RUN_NAME]"
echo "  Compare runs:        ./compare_runs.sh RUN1 RUN2"
echo "  View result:         cat results/[RUN_NAME]/question_1.txt"
echo "  Delete run:          rm -rf results/[RUN_NAME]"
echo ""

