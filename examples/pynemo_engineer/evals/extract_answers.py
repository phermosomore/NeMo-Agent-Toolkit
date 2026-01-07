#!/usr/bin/env python3
"""
Extract Final Answers from Evaluation Results

This script processes evaluation result files and extracts questions and their
final answers into a single Markdown file.

Usage:
    python extract_answers.py RUN_NAME [--output OUTPUT_FILE]
    python extract_answers.py results/run_20260107_154802 --output answers.md
"""

import argparse
import re
import sys
from pathlib import Path
from typing import Optional, Tuple


def extract_question(content: str) -> Optional[str]:
    """Extract the question from the result file content."""
    # Find the QUESTION section
    question_match = re.search(
        r"={40,}\s*QUESTION \d+\s*={40,}\s*\n(.*?)\n={40,}",
        content,
        re.DOTALL
    )
    
    if question_match:
        question = question_match.group(1).strip()
        return question
    return None


def extract_final_answer(content: str) -> Optional[str]:
    """Extract the final answer from the result file content."""
    # Look for "Final Answer:" in the content
    # Handle both "Final Answer: text" and "Final Answer:\ntext" formats
    final_answer_match = re.search(
        r"Final Answer:\s*(.*?)(?:\[39m|\[32mWorkflow Result:|={40,}|------------------------------)",
        content,
        re.DOTALL
    )
    
    if final_answer_match:
        answer = final_answer_match.group(1).strip()
        # Clean up the answer - remove ALL ANSI escape codes and control characters
        answer = re.sub(r'\x1b\[[0-9;]*m', '', answer)  # Remove ANSI escape codes (\x1b[XXm)
        answer = re.sub(r'\x1b', '', answer)             # Remove any remaining escape chars
        answer = re.sub(r'\[\d+m', '', answer)           # Remove bracket color codes
        answer = re.sub(r'\[0m', '', answer)             # Remove reset codes
        
        # Remove any trailing separators or workflow result text
        answer = re.sub(r'\s*\[.*?Workflow Result:.*$', '', answer, flags=re.DOTALL)
        
        return answer.strip()
    
    return None


def process_result_file(file_path: Path) -> Optional[Tuple[str, str]]:
    """Process a single result file and extract question and answer."""
    try:
        content = file_path.read_text(encoding='utf-8', errors='ignore')
        
        question = extract_question(content)
        answer = extract_final_answer(content)
        
        if question and answer:
            return (question, answer)
        else:
            print(f"Warning: Could not extract question or answer from {file_path.name}")
            return None
            
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return None


def create_markdown_report(results_dir: Path, output_file: Path) -> None:
    """Create a markdown report with all questions and answers."""
    
    # Find all question files
    question_files = sorted(
        results_dir.glob("question_*.txt"),
        key=lambda x: int(re.search(r'question_(\d+)', x.name).group(1))
    )
    
    if not question_files:
        print(f"Error: No question files found in {results_dir}")
        sys.exit(1)
    
    # Extract questions and answers
    qa_pairs = []
    for question_file in question_files:
        result = process_result_file(question_file)
        if result:
            qa_pairs.append(result)
    
    if not qa_pairs:
        print("Error: No questions and answers could be extracted")
        sys.exit(1)
    
    # Create markdown content
    run_name = results_dir.name
    markdown_lines = [
        f"# Evaluation Results: {run_name}",
        "",
        f"This document contains the questions and final answers from the evaluation run.",
        "",
        f"**Total Questions:** {len(qa_pairs)}",
        "",
        "---",
        ""
    ]
    
    # Add each question and answer
    for i, (question, answer) in enumerate(qa_pairs, 1):
        markdown_lines.extend([
            f"## Question {i}",
            "",
            f"**Q:** {question}",
            "",
            "**Answer:**",
            "",
            answer,
            "",
            "---",
            ""
        ])
    
    # Write to output file
    markdown_content = "\n".join(markdown_lines)
    output_file.write_text(markdown_content, encoding='utf-8')
    
    print(f"✓ Successfully created markdown report")
    print(f"  Questions processed: {len(qa_pairs)}")
    print(f"  Output file: {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description="Extract questions and final answers from evaluation results into a Markdown file",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Extract from run name
  python extract_answers.py run_20260107_154802
  
  # Extract with custom output file
  python extract_answers.py run_20260107_154802 --output my_answers.md
  
  # Extract from full path
  python extract_answers.py results/run_20260107_154802 --output answers.md
        """
    )
    
    parser.add_argument(
        'run_name',
        help='Run name or path to results directory (e.g., run_20260107_154802 or results/run_20260107_154802)'
    )
    
    parser.add_argument(
        '-o', '--output',
        default=None,
        help='Output markdown file path (default: results/{RUN_NAME}/final_answers.md)'
    )
    
    args = parser.parse_args()
    
    # Determine the script directory
    script_dir = Path(__file__).parent
    
    # Determine results directory
    run_path = Path(args.run_name)
    
    if run_path.is_dir():
        # User provided full path
        results_dir = run_path
    else:
        # User provided run name, assume it's in results/
        results_dir = script_dir / "results" / args.run_name
        
        if not results_dir.is_dir():
            print(f"Error: Results directory not found: {results_dir}")
            print(f"Expected either:")
            print(f"  - A valid directory path")
            print(f"  - A run name in {script_dir / 'results'}")
            sys.exit(1)
    
    # Determine output file
    if args.output:
        output_file = Path(args.output)
    else:
        output_file = results_dir / "final_answers.md"
    
    print(f"Processing results from: {results_dir}")
    print(f"Output file: {output_file}")
    print()
    
    # Create the report
    create_markdown_report(results_dir, output_file)


if __name__ == "__main__":
    main()

