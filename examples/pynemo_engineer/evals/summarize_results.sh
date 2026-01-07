#!/bin/bash

# Summary Script for Evaluation Results
# Provides a quick overview of evaluation run
#
# Usage: ./summarize_results.sh [RUN_NAME]
#   RUN_NAME: Optional name of the evaluation run to summarize
#             If not provided, lists all available runs and uses the most recent

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_BASE_DIR="${SCRIPT_DIR}/results"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if results base directory exists
if [ ! -d "${RESULTS_BASE_DIR}" ]; then
    echo -e "${RED}Error: Results directory not found at ${RESULTS_BASE_DIR}${NC}"
    echo "Run ./run_eval.sh first to generate results."
    exit 1
fi

# Determine which run to summarize
if [ -n "$1" ]; then
    RUN_NAME="$1"
    RESULTS_DIR="${RESULTS_BASE_DIR}/${RUN_NAME}"
else
    # List available runs
    echo -e "${BLUE}Available evaluation runs:${NC}"
    echo ""
    runs=($(ls -1t "${RESULTS_BASE_DIR}" 2>/dev/null | grep -v ".gitkeep"))
    
    if [ ${#runs[@]} -eq 0 ]; then
        echo -e "${YELLOW}No evaluation runs found in ${RESULTS_BASE_DIR}${NC}"
        echo "Run ./run_eval.sh to generate results."
        exit 0
    fi
    
    for run in "${runs[@]}"; do
        run_dir="${RESULTS_BASE_DIR}/${run}"
        if [ -d "$run_dir" ]; then
            question_count=$(find "$run_dir" -name "question_*.txt" 2>/dev/null | wc -l | tr -d ' ')
            timestamp=""
            if [ -f "$run_dir/run_summary.txt" ]; then
                timestamp=$(grep "^Date:" "$run_dir/run_summary.txt" | sed 's/Date: //' 2>/dev/null)
            fi
            echo "  - ${run} (${question_count} questions) ${timestamp}"
        fi
    done
    echo ""
    
    # Use the most recent run
    RUN_NAME="${runs[0]}"
    RESULTS_DIR="${RESULTS_BASE_DIR}/${RUN_NAME}"
    echo -e "${YELLOW}Using most recent run: ${RUN_NAME}${NC}"
    echo ""
fi

echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}  Evaluation Results Summary${NC}"
echo -e "${BLUE}================================================${NC}"
echo ""
echo "Run name: ${RUN_NAME}"
echo ""

# Check if specific results directory exists
if [ ! -d "${RESULTS_DIR}" ]; then
    echo -e "${RED}Error: Results directory not found at ${RESULTS_DIR}${NC}"
    echo ""
    echo "Available runs:"
    ls -1 "${RESULTS_BASE_DIR}" | grep -v ".gitkeep"
    exit 1
fi

# Count total result files
total_files=$(find "${RESULTS_DIR}" -name "question_*.txt" | wc -l | tr -d ' ')

if [ "$total_files" -eq 0 ]; then
    echo -e "${YELLOW}No result files found in ${RESULTS_DIR}${NC}"
    echo "Run ./run_eval.sh to generate results."
    exit 0
fi

echo "Total questions evaluated: ${total_files}"
echo ""

# Check for errors
error_count=$(grep -l "ERROR:" "${RESULTS_DIR}"/question_*.txt 2>/dev/null | wc -l | tr -d ' ')
success_count=$((total_files - error_count))

echo -e "${GREEN}Successful: ${success_count}${NC}"
echo -e "${RED}Failed: ${error_count}${NC}"
echo ""

# Show file sizes
echo "Result file sizes:"
ls -lh "${RESULTS_DIR}"/question_*.txt | awk '{printf "  %-25s %8s\n", $9, $5}'
echo ""

# Show questions that failed (if any)
if [ "$error_count" -gt 0 ]; then
    echo -e "${RED}Failed Questions:${NC}"
    for file in "${RESULTS_DIR}"/question_*.txt; do
        if grep -q "ERROR:" "$file"; then
            question_num=$(basename "$file" .txt | sed 's/question_//')
            echo -e "  ${RED}✗${NC} Question ${question_num}"
            # Extract and show first line of question
            sed -n '/^QUESTION/,/^===/p' "$file" | grep -v "^===" | grep -v "^QUESTION" | head -1 | sed 's/^/    /'
        fi
    done
    echo ""
fi

# Show timestamps
echo "Evaluation times:"
for file in "${RESULTS_DIR}"/question_*.txt; do
    question_num=$(basename "$file" .txt | sed 's/question_//')
    timestamp=$(grep "Completed at:" "$file" | sed 's/Completed at: //')
    if [ -n "$timestamp" ]; then
        echo "  Question ${question_num}: ${timestamp}"
    fi
done
echo ""

# Quick stats
total_size=$(du -sh "${RESULTS_DIR}" | awk '{print $1}')
echo "Total results size: ${total_size}"
echo ""

echo -e "${BLUE}================================================${NC}"
echo ""
echo "To view individual results:"
echo "  cat ${RESULTS_DIR}/question_1.txt"
echo ""
echo "To search across all results:"
echo "  grep -i 'search-term' ${RESULTS_DIR}/*.txt"
echo ""
echo "To compare with other runs:"
echo "  ./summarize_results.sh [RUN_NAME]"
echo ""

