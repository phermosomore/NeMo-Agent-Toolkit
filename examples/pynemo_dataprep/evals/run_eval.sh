#!/bin/bash

# Evaluation Script for NeMo Agent Toolkit
# Runs all questions from questions.txt and saves results to individual files

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
QUESTIONS_FILE="${SCRIPT_DIR}/questions.txt"
RESULTS_DIR="${SCRIPT_DIR}/results"
CONFIG_FILE="examples/pynemo_dataprep/configs/config.yaml"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Create results directory if it doesn't exist
mkdir -p "${RESULTS_DIR}"

echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}  NeMo Agent Toolkit - Evaluation Runner${NC}"
echo -e "${BLUE}================================================${NC}"
echo ""
echo "Questions file: ${QUESTIONS_FILE}"
echo "Results directory: ${RESULTS_DIR}"
echo "Config file: ${CONFIG_FILE}"
echo ""

# Check if questions file exists
if [ ! -f "${QUESTIONS_FILE}" ]; then
    echo -e "${RED}Error: Questions file not found at ${QUESTIONS_FILE}${NC}"
    exit 1
fi

# Parse questions from file (blank line separated)
question_num=0
current_question=""

while IFS= read -r line || [ -n "$line" ]; do
    # If line is blank and we have accumulated a question, process it
    if [ -z "$line" ] && [ -n "$current_question" ]; then
        question_num=$((question_num + 1))
        result_file="${RESULTS_DIR}/question_${question_num}.txt"
        
        echo -e "${GREEN}Running Question ${question_num}...${NC}"
        echo "Question: ${current_question:0:80}..."
        echo ""
        
        # Write question to result file
        {
            echo "================================================"
            echo "QUESTION ${question_num}"
            echo "================================================"
            echo ""
            echo "${current_question}"
            echo ""
            echo "================================================"
            echo "RESPONSE"
            echo "================================================"
            echo ""
        } > "${result_file}"
        
        # Run nat command and append output to result file
        echo "Running: nat run --config_file=${CONFIG_FILE} --input \"${current_question}\""
        echo ""
        
        if nat run --config_file="${CONFIG_FILE}" --input "${current_question}" >> "${result_file}" 2>&1; then
            echo -e "${GREEN}✓ Question ${question_num} completed${NC}"
        else
            echo -e "${RED}✗ Question ${question_num} failed${NC}"
            echo ""
            echo "ERROR: Command failed for question ${question_num}" >> "${result_file}"
        fi
        
        # Add timestamp to result file
        {
            echo ""
            echo "================================================"
            echo "Completed at: $(date)"
            echo "================================================"
        } >> "${result_file}"
        
        echo ""
        echo "---"
        echo ""
        
        # Reset for next question
        current_question=""
    elif [ -n "$line" ]; then
        # Accumulate non-blank lines into current question
        if [ -z "$current_question" ]; then
            current_question="$line"
        else
            current_question="${current_question}"$'\n'"${line}"
        fi
    fi
done < "${QUESTIONS_FILE}"

# Handle last question if file doesn't end with blank line
if [ -n "$current_question" ]; then
    question_num=$((question_num + 1))
    result_file="${RESULTS_DIR}/question_${question_num}.txt"
    
    echo -e "${GREEN}Running Question ${question_num}...${NC}"
    echo "Question: ${current_question:0:80}..."
    echo ""
    
    {
        echo "================================================"
        echo "QUESTION ${question_num}"
        echo "================================================"
        echo ""
        echo "${current_question}"
        echo ""
        echo "================================================"
        echo "RESPONSE"
        echo "================================================"
        echo ""
    } > "${result_file}"
    
    echo "Running: nat run --config_file=${CONFIG_FILE} --input \"${current_question}\""
    echo ""
    
    if nat run --config_file="${CONFIG_FILE}" --input "${current_question}" >> "${result_file}" 2>&1; then
        echo -e "${GREEN}✓ Question ${question_num} completed${NC}"
    else
        echo -e "${RED}✗ Question ${question_num} failed${NC}"
        echo ""
        echo "ERROR: Command failed for question ${question_num}" >> "${result_file}"
    fi
    
    {
        echo ""
        echo "================================================"
        echo "Completed at: $(date)"
        echo "================================================"
    } >> "${result_file}"
    
    echo ""
fi

# Summary
echo ""
echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}  Evaluation Complete!${NC}"
echo -e "${BLUE}================================================${NC}"
echo ""
echo "Total questions processed: ${question_num}"
echo "Results saved in: ${RESULTS_DIR}"
echo ""
echo "To view results:"
echo "  ls -lh ${RESULTS_DIR}"
echo ""

