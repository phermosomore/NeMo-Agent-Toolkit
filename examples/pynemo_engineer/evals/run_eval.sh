#!/bin/bash

# Evaluation Script for NeMo Agent Toolkit
# Runs all questions from questions.txt and saves results to individual files
#
# Usage: ./run_eval.sh [OPTIONS] [RUN_NAME]
#   RUN_NAME: Optional name for this evaluation run (default: timestamp)
#
# Options:
#   --retry              Enable retry on failure (useful for network timeouts)
#   --max-retries N      Maximum number of retry attempts (default: 3)
#   --retry-delay N      Delay between retries in seconds (default: 5)
#   --help               Show this help message

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
QUESTIONS_FILE="${SCRIPT_DIR}/questions.txt"
CONFIG_FILE="examples/pynemo_engineer/configs/config.yaml"

# Default retry settings
RETRY_ENABLED=false
MAX_RETRIES=3
RETRY_DELAY=5

# Parse command line arguments
RUN_NAME=""
while [[ $# -gt 0 ]]; do
    case $1 in
        --retry)
            RETRY_ENABLED=true
            shift
            ;;
        --max-retries)
            MAX_RETRIES="$2"
            shift 2
            ;;
        --retry-delay)
            RETRY_DELAY="$2"
            shift 2
            ;;
        --help)
            echo "Usage: ./run_eval.sh [OPTIONS] [RUN_NAME]"
            echo ""
            echo "Options:"
            echo "  --retry              Enable retry on failure (useful for network timeouts)"
            echo "  --max-retries N      Maximum number of retry attempts (default: 3)"
            echo "  --retry-delay N      Delay between retries in seconds (default: 5)"
            echo "  --help               Show this help message"
            echo ""
            echo "Arguments:"
            echo "  RUN_NAME             Optional name for this evaluation run (default: timestamp)"
            exit 0
            ;;
        *)
            if [ -z "$RUN_NAME" ]; then
                RUN_NAME="$1"
            else
                echo "Error: Unknown argument: $1"
                echo "Use --help for usage information"
                exit 1
            fi
            shift
            ;;
    esac
done

# Get run name from argument or generate timestamp
if [ -z "$RUN_NAME" ]; then
    RUN_NAME="run_$(date +%Y%m%d_%H%M%S)"
fi

# Set results directory based on run name
RESULTS_DIR="${SCRIPT_DIR}/results/${RUN_NAME}"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Create results directory if it doesn't exist
if [ -d "${RESULTS_DIR}" ]; then
    echo -e "${YELLOW}Warning: Results directory already exists: ${RESULTS_DIR}${NC}"
    echo -e "${YELLOW}Results will be overwritten.${NC}"
    echo ""
fi
mkdir -p "${RESULTS_DIR}"

echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}  NeMo Agent Toolkit - Evaluation Runner${NC}"
echo -e "${BLUE}================================================${NC}"
echo ""
echo "Run name: ${RUN_NAME}"
echo "Questions file: ${QUESTIONS_FILE}"
echo "Results directory: ${RESULTS_DIR}"
echo "Config file: ${CONFIG_FILE}"
if [ "$RETRY_ENABLED" = true ]; then
    echo -e "${YELLOW}Retry enabled: Max ${MAX_RETRIES} retries, ${RETRY_DELAY}s delay${NC}"
fi
echo ""

# Check if questions file exists
if [ ! -f "${QUESTIONS_FILE}" ]; then
    echo -e "${RED}Error: Questions file not found at ${QUESTIONS_FILE}${NC}"
    exit 1
fi

# Function to run a question with retry logic
run_question_with_retry() {
    local question="$1"
    local result_file="$2"
    local question_num="$3"
    local attempt=1
    local success=false
    
    while [ $attempt -le $((MAX_RETRIES + 1)) ]; do
        if [ $attempt -gt 1 ]; then
            echo -e "${YELLOW}Retry attempt ${attempt}/${MAX_RETRIES} for question ${question_num}...${NC}" | tee -a "${result_file}"
            echo "" >> "${result_file}"
            sleep "${RETRY_DELAY}"
        fi
        
        # Run nat command
        if nat run --config_file="${CONFIG_FILE}" --input "${question}" >> "${result_file}" 2>&1; then
            success=true
            break
        else
            if [ $attempt -le $MAX_RETRIES ] && [ "$RETRY_ENABLED" = true ]; then
                echo "" >> "${result_file}"
                echo "---" >> "${result_file}"
                echo "Attempt ${attempt} failed, retrying..." >> "${result_file}"
                echo "---" >> "${result_file}"
                echo "" >> "${result_file}"
            else
                echo "" >> "${result_file}"
                echo "ERROR: Command failed for question ${question_num}" >> "${result_file}"
            fi
        fi
        
        attempt=$((attempt + 1))
        
        # If retry is not enabled, break after first attempt
        if [ "$RETRY_ENABLED" = false ]; then
            break
        fi
    done
    
    if [ "$success" = true ]; then
        return 0
    else
        return 1
    fi
}

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
        
        if run_question_with_retry "${current_question}" "${result_file}" "${question_num}"; then
            echo -e "${GREEN}✓ Question ${question_num} completed${NC}"
        else
            echo -e "${RED}✗ Question ${question_num} failed after all retries${NC}"
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
    
    if run_question_with_retry "${current_question}" "${result_file}" "${question_num}"; then
        echo -e "${GREEN}✓ Question ${question_num} completed${NC}"
    else
        echo -e "${RED}✗ Question ${question_num} failed after all retries${NC}"
    fi
    
    {
        echo ""
        echo "================================================"
        echo "Completed at: $(date)"
        echo "================================================"
    } >> "${result_file}"
    
    echo ""
fi

# Create summary file
SUMMARY_FILE="${RESULTS_DIR}/run_summary.txt"
{
    echo "================================================"
    echo "EVALUATION RUN SUMMARY"
    echo "================================================"
    echo ""
    echo "Run name: ${RUN_NAME}"
    echo "Date: $(date)"
    echo "Total questions: ${question_num}"
    echo "Config file: ${CONFIG_FILE}"
    echo "Questions file: ${QUESTIONS_FILE}"
    if [ "$RETRY_ENABLED" = true ]; then
        echo "Retry enabled: Max ${MAX_RETRIES} retries, ${RETRY_DELAY}s delay"
    fi
    echo ""
    echo "================================================"
    echo "RESULTS"
    echo "================================================"
    echo ""
    for i in $(seq 1 $question_num); do
        result_file="${RESULTS_DIR}/question_${i}.txt"
        if [ -f "$result_file" ]; then
            if grep -q "ERROR:" "$result_file"; then
                echo "Question ${i}: FAILED"
            else
                echo "Question ${i}: SUCCESS"
            fi
        fi
    done
    echo ""
} > "${SUMMARY_FILE}"

# Summary
echo ""
echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}  Evaluation Complete!${NC}"
echo -e "${BLUE}================================================${NC}"
echo ""
echo "Run name: ${RUN_NAME}"
echo "Total questions processed: ${question_num}"
if [ "$RETRY_ENABLED" = true ]; then
    echo -e "${YELLOW}Retry was enabled (max ${MAX_RETRIES} retries)${NC}"
fi
echo "Results saved in: ${RESULTS_DIR}"
echo ""
echo "To view results:"
echo "  ls -lh ${RESULTS_DIR}"
echo "  cat ${SUMMARY_FILE}"
echo ""
echo "To view summary:"
echo "  ./summarize_results.sh ${RUN_NAME}"
echo ""





