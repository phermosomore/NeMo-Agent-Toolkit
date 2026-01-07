# Performance Tracing and Bottleneck Analysis Guide

This guide explains how to use the built-in tracing features to identify performance bottlenecks in the PyNemo Engineer workflow.

## Quick Start

### 1. Run Your Workflow with Tracing Enabled

The config file is already set up with tracing. Just run your workflow as normal:

```bash
cd examples/pynemo_engineer
nat run --config_file configs/config.yaml --input "What is DoMINO?"
```

This will create a trace file: `pynemo_engineer_traces.jsonl`

### 2. Analyze the Traces

Run the analysis script to see a detailed breakdown of where time is spent:

```bash
python scripts/analyze_traces.py
```

Or specify a custom trace file:

```bash
python scripts/analyze_traces.py path/to/traces.jsonl
```

## What You'll See

The analysis script provides:

### 📊 Summary Statistics
- Total number of spans (function calls, LLM calls, etc.)
- Unique operation types
- Total execution time

### 🤖 LLM Call Analysis (Main Bottleneck)
- **Total LLM calls**: How many times the LLM was invoked
- **Total LLM time**: Time spent waiting for LLM responses
- **Percentage of total time**: Usually 70-90% for agent workflows
- **Slowest LLM calls**: Top 5 longest LLM invocations with model names

### 🔧 Tool Call Analysis
- Total tool executions
- Breakdown by tool type (retriever, code_generation, code_execution)
- Average time per tool

### 📚 Retriever Call Analysis
- Time spent on vector database queries
- Number of retrieval operations

### 💡 Recommendations
Automatic suggestions based on your performance profile

## Viewing Real-Time Progress

If you want to see progress on the console as it runs, change the logging level in `config.yaml`:

```yaml
general:
  telemetry:
    logging:
      console:
        _type: console
        level: DEBUG  # Change from INFO to DEBUG for more detail
```

## Understanding the Results

### Typical Bottlenecks

1. **LLM Calls (70-90% of time)**
   - The reasoning agent calls the LLM multiple times
   - Each ReAct iteration requires LLM inference
   - DeepSeek-V3.2 is powerful but slower than smaller models

2. **Retriever Calls (5-15% of time)**
   - Milvus vector searches
   - Embedding generation for queries
   - Can be optimized by reducing `top_k`

3. **Code Execution (Variable)**
   - Depends on what code is generated
   - Sandbox overhead is minimal

## Optimization Strategies

### If LLM calls are the bottleneck (>70% of time):

1. **Use a faster model:**
   ```yaml
   llms:
     nim_llm:
       model_name: meta/llama-3.3-70b-instruct  # Faster than deepseek-v3.2
       temperature: 0.6
   ```

2. **Reduce max_tokens:**
   ```yaml
   llms:
     nim_llm:
       max_tokens: 16384  # Instead of 32768
   ```

3. **Lower temperature for faster sampling:**
   ```yaml
   llms:
     nim_llm:
       temperature: 0.1  # Closer to greedy decoding = faster
   ```

4. **Reduce retry attempts:**
   ```yaml
   functions:
     react_agent:
       parse_agent_response_max_retries: 2  # Instead of 4
   ```

5. **Switch to ReWOO agent** (plans once, executes in parallel):
   ```yaml
   workflow:
     _type: rewoo_agent  # Instead of reasoning_agent + react_agent
     # ... other config
   ```

### If retriever calls are slow:

1. **Reduce top_k:**
   ```yaml
   retrievers:
     physicsnemo_docs_retriever:
       top_k: 5  # Instead of 10
   ```

2. **Use a faster embedding model:**
   ```yaml
   embedders:
     milvus_embedder:
       model_name: nvidia/nv-embedqa-e5-v5  # Smaller, faster
   ```

## Advanced Tracing Options

### Console Output with Timestamps

To see each step with timing on the console:

```yaml
general:
  telemetry:
    logging:
      console:
        _type: console
        level: INFO
    tracing:
      console_trace:
        _type: console_trace  # If available
      trace_file:
        _type: file
        output_path: pynemo_engineer_traces.jsonl
```

### Using Phoenix UI for Visual Analysis

For a web-based UI to analyze traces:

1. Install Phoenix:
   ```bash
   uv pip install -e '.[phoenix]'
   uv pip install arize-phoenix
   ```

2. Start Phoenix server:
   ```bash
   phoenix serve
   ```

3. Update config:
   ```yaml
   general:
     telemetry:
       tracing:
         phoenix:
           _type: phoenix
           endpoint: http://localhost:6006/v1/traces
           project: pynemo_engineer
   ```

4. View traces at: http://localhost:6006

## Comparing Multiple Runs

To compare performance across different configurations:

```bash
# Run 1: Baseline
nat run --config_file configs/config.yaml --input "What is DoMINO?" 
mv pynemo_engineer_traces.jsonl traces_baseline.jsonl

# Run 2: Optimized
# (modify config with faster model)
nat run --config_file configs/config.yaml --input "What is DoMINO?"
mv pynemo_engineer_traces.jsonl traces_optimized.jsonl

# Analyze both
python scripts/analyze_traces.py traces_baseline.jsonl > analysis_baseline.txt
python scripts/analyze_traces.py traces_optimized.jsonl > analysis_optimized.txt
```

## Trace File Format

The trace file uses OpenTelemetry JSONL format:
- Each line is a JSON object containing spans
- Spans have start/end times in nanoseconds
- Attributes contain metadata (model name, tokens, etc.)

You can process this with any OpenTelemetry-compatible tool.

## Troubleshooting

### No trace file generated?
- Check that the config has the `general.telemetry` section
- Verify the workflow runs without errors
- Check file permissions in the directory

### Empty or incomplete traces?
- Make sure the workflow completes successfully
- Check for errors in the console output
- Try changing `mode: overwrite` instead of `append`

### Analysis script shows no LLM calls?
- The workflow might not have used the LLM yet
- Check that the query actually triggered agent execution
- Verify the trace file has content: `wc -l pynemo_engineer_traces.jsonl`

## Example Output

```
================================================================================
🔍 PYNEMO ENGINEER WORKFLOW - PERFORMANCE ANALYSIS
================================================================================

📊 SUMMARY STATISTICS
--------------------------------------------------------------------------------
Total spans recorded: 47
Unique span types: 15
Total estimated duration: 45231.42 ms (45.23 seconds)

🤖 LLM CALLS (Potential Bottleneck)
--------------------------------------------------------------------------------
Total LLM calls: 8
Total LLM time: 38450.23 ms (38.45 seconds)
Average LLM call: 4806.28 ms
Percentage of total time: 85.0%

   Slowest LLM Calls:
   1.  5234.56 ms - LLM.chat (Model: deepseek-ai/deepseek-v3.2)
   2.  5123.45 ms - LLM.chat (Model: deepseek-ai/deepseek-v3.2)
   3.  4987.65 ms - LLM.chat (Model: deepseek-ai/deepseek-v3.2)

💡 RECOMMENDATIONS
--------------------------------------------------------------------------------
⚠️  LLM calls account for >70% of execution time. Consider:
   • Using a faster model for the ReAct agent
   • Reducing max_tokens to speed up generation
   • Using temperature=0 for faster, deterministic responses
```

## Additional Resources

- [NAT Observability Documentation](../../docs/source/run-workflows/observe/observe.md)
- [NAT Profiler Guide](../../docs/source/improve-workflows/profiler.md)
- [OpenTelemetry Documentation](https://opentelemetry.io/docs/)

