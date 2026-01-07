#!/bin/bash

# Comparison Script for Evaluation Runs
# Compares results between two evaluation runs
#
# Usage: ./compare_runs.sh RUN1 RUN2

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_BASE_DIR="${SCRIPT_DIR}/results"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check arguments
if [ "$#" -lt 2 ]; then
    echo -e "${RED}Error: Two run names required${NC}"
    echo ""
    echo "Usage: $0 RUN1 RUN2"
    echo ""
    echo "Available runs:"
    ls -1 "${RESULTS_BASE_DIR}" 2>/dev/null | grep -v ".gitkeep"
    exit 1
fi

RUN1="$1"
RUN2="$2"
RUN1_DIR="${RESULTS_BASE_DIR}/${RUN1}"
RUN2_DIR="${RESULTS_BASE_DIR}/${RUN2}"

# Check if both runs exist
if [ ! -d "${RUN1_DIR}" ]; then
    echo -e "${RED}Error: Run '${RUN1}' not found at ${RUN1_DIR}${NC}"
    exit 1
fi

if [ ! -d "${RUN2_DIR}" ]; then
    echo -e "${RED}Error: Run '${RUN2}' not found at ${RUN2_DIR}${NC}"
    exit 1
fi

echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}  Comparing Evaluation Runs${NC}"
echo -e "${BLUE}================================================${NC}"
echo ""

# Get run metadata
echo -e "${BLUE}Run 1: ${RUN1}${NC}"
if [ -f "${RUN1_DIR}/run_summary.txt" ]; then
    grep "^Date:" "${RUN1_DIR}/run_summary.txt" | sed 's/^/  /'
    grep "^Config file:" "${RUN1_DIR}/run_summary.txt" | sed 's/^/  /'
fi
echo ""

echo -e "${BLUE}Run 2: ${RUN2}${NC}"
if [ -f "${RUN2_DIR}/run_summary.txt" ]; then
    grep "^Date:" "${RUN2_DIR}/run_summary.txt" | sed 's/^/  /'
    grep "^Config file:" "${RUN2_DIR}/run_summary.txt" | sed 's/^/  /'
fi
echo ""

# Count questions
run1_count=$(find "${RUN1_DIR}" -name "question_*.txt" | wc -l | tr -d ' ')
run2_count=$(find "${RUN2_DIR}" -name "question_*.txt" | wc -l | tr -d ' ')

echo "================================================"
echo "Question Counts"
echo "================================================"
echo "Run 1: ${run1_count} questions"
echo "Run 2: ${run2_count} questions"
echo ""

# Compare success/failure rates
echo "================================================"
echo "Success/Failure Comparison"
echo "================================================"

run1_errors=$(grep -l "ERROR:" "${RUN1_DIR}"/question_*.txt 2>/dev/null | wc -l | tr -d ' ')
run1_success=$((run1_count - run1_errors))

run2_errors=$(grep -l "ERROR:" "${RUN2_DIR}"/question_*.txt 2>/dev/null | wc -l | tr -d ' ')
run2_success=$((run2_count - run2_errors))

echo "Run 1: ${run1_success} success, ${run1_errors} failed"
echo "Run 2: ${run2_success} success, ${run2_errors} failed"
echo ""

# Question-by-question comparison
echo "================================================"
echo "Question-by-Question Comparison"
echo "================================================"
echo ""

max_questions=$((run1_count > run2_count ? run1_count : run2_count))

for i in $(seq 1 $max_questions); do
    run1_file="${RUN1_DIR}/question_${i}.txt"
    run2_file="${RUN2_DIR}/question_${i}.txt"
    
    run1_status="MISSING"
    run2_status="MISSING"
    
    if [ -f "$run1_file" ]; then
        if grep -q "ERROR:" "$run1_file"; then
            run1_status="FAILED"
        else
            run1_status="SUCCESS"
        fi
    fi
    
    if [ -f "$run2_file" ]; then
        if grep -q "ERROR:" "$run2_file"; then
            run2_status="FAILED"
        else
            run2_status="SUCCESS"
        fi
    fi
    
    # Color coding
    if [ "$run1_status" = "SUCCESS" ]; then
        run1_display="${GREEN}${run1_status}${NC}"
    elif [ "$run1_status" = "FAILED" ]; then
        run1_display="${RED}${run1_status}${NC}"
    else
        run1_display="${YELLOW}${run1_status}${NC}"
    fi
    
    if [ "$run2_status" = "SUCCESS" ]; then
        run2_display="${GREEN}${run2_status}${NC}"
    elif [ "$run2_status" = "FAILED" ]; then
        run2_display="${RED}${run2_status}${NC}"
    else
        run2_display="${YELLOW}${run2_status}${NC}"
    fi
    
    # Show comparison indicator
    if [ "$run1_status" = "$run2_status" ]; then
        indicator="  "
    elif [ "$run1_status" = "SUCCESS" ] && [ "$run2_status" != "SUCCESS" ]; then
        indicator="${GREEN}←${NC}"
    elif [ "$run2_status" = "SUCCESS" ] && [ "$run1_status" != "SUCCESS" ]; then
        indicator="${GREEN}→${NC}"
    else
        indicator="${YELLOW}↔${NC}"
    fi
    
    echo -e "Question ${i}: ${run1_display} ${indicator} ${run2_display}"
done

echo ""
echo "================================================"
echo "Legend"
echo "================================================"
echo -e "${GREEN}← ${NC}Run 1 better   ${GREEN}→${NC} Run 2 better   ${YELLOW}↔${NC} Different but neither better"
echo ""

# File size comparison
echo "================================================"
echo "Total Result Size Comparison"
echo "================================================"
run1_size=$(du -sh "${RUN1_DIR}" | awk '{print $1}')
run2_size=$(du -sh "${RUN2_DIR}" | awk '{print $1}')
echo "Run 1: ${run1_size}"
echo "Run 2: ${run2_size}"
echo ""

echo "To view detailed differences for a specific question:"
echo "  diff ${RUN1_DIR}/question_1.txt ${RUN2_DIR}/question_1.txt"
echo ""

