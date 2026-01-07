# Quick Tracing Reference

## ⚡ Fast Track: See Your Bottlenecks in 3 Steps

### Step 1: Run with tracing (already configured!)
```bash
cd examples/pynemo_engineer
nat run --config_file configs/config.yaml --input "What is DoMINO?"
```

### Step 2: Analyze the traces
```bash
python scripts/analyze_traces.py
```

### Step 3: Look for the bottleneck
- **LLM calls >70%** → Your model is too slow
- **Retriever calls >20%** → Vector search needs optimization  
- **Code execution >30%** → Generated code is expensive

---

## 🎯 Most Common Fix: Speed Up LLM

Your current config uses `deepseek-ai/deepseek-v3.2` which is powerful but **SLOW**.

### Option A: Much Faster Model (Recommended)
```yaml
llms:
  nim_llm:
    _type: nim
    model_name: meta/llama-3.3-70b-instruct  # 2-3x faster
    temperature: 0.6
    top_p: 0.95
    max_tokens: 16384  # Reduced from 32768
```

### Option B: Fastest Model (Good for Development)
```yaml
llms:
  nim_llm:
    _type: nim
    model_name: meta/llama-3.1-70b-instruct  # Fastest 70B
    temperature: 0.0  # Greedy = faster
    max_tokens: 8192
```

### Option C: Keep DeepSeek but Optimize
```yaml
llms:
  nim_llm:
    model_name: deepseek-ai/deepseek-v3.2
    temperature: 0.5  # Reduced from 1.0
    max_tokens: 16384  # Reduced from 32768
```

---

## 📊 What the Analysis Shows

### Good Performance
```
🤖 LLM CALLS
Total LLM time: 8450.23 ms (8.45 seconds)
Percentage of total time: 45.0%
```
✅ LLM is <50% of time - well optimized!

### Needs Optimization  
```
🤖 LLM CALLS
Total LLM time: 38450.23 ms (38.45 seconds)
Percentage of total time: 85.0%
```
⚠️ LLM is >80% of time - switch to faster model!

---

## 🔧 Other Quick Fixes

### Reduce Retriever Time
In `config.yaml`, change:
```yaml
retrievers:
  physicsnemo_docs_retriever:
    top_k: 5  # Changed from 10 - faster, still good results
```

### Reduce Agent Retries
In `config.yaml`, change:
```yaml
functions:
  react_agent:
    parse_agent_response_max_retries: 2  # Changed from 4
```

### Use Reasoning Agent Only When Needed
For simple queries, you might not need the reasoning wrapper:
```yaml
workflow:
  _type: react_agent  # Direct agent, no reasoning wrapper
  # Remove: _type: reasoning_agent
  # Remove: augmented_fn: react_agent
```

---

## 📈 Before/After Example

### Before (Slow)
```
Model: deepseek-ai/deepseek-v3.2
Temperature: 1.0
Max tokens: 32768
Parse retries: 4
Top_k: 10

Result: 45 seconds per query
LLM calls: 85% of time
```

### After (Fast)  
```
Model: meta/llama-3.3-70b-instruct
Temperature: 0.6
Max tokens: 16384
Parse retries: 2
Top_k: 5

Result: 12 seconds per query
LLM calls: 55% of time
```

**Speed improvement: 3.75x faster! 🚀**

---

## 🎨 Want Visual Analysis?

### Install Phoenix (takes 2 minutes)
```bash
uv pip install -e '.[phoenix]'
uv pip install arize-phoenix
```

### Start Phoenix Server
```bash
phoenix serve
```

### Update config.yaml
```yaml
general:
  telemetry:
    tracing:
      phoenix:
        _type: phoenix
        endpoint: http://localhost:6006/v1/traces
        project: pynemo_engineer
```

### View in Browser
Open: http://localhost:6006

You'll see a beautiful timeline of all operations with timing!

---

## ❓ Troubleshooting

**Q: No trace file generated?**  
A: Check the directory - file is named `pynemo_engineer_traces.jsonl`

**Q: Analysis shows 0 LLM calls?**  
A: Query was too simple or failed early. Try a complex question.

**Q: I want to see timing WHILE it runs, not after**  
A: Change logging level to DEBUG:
```yaml
general:
  telemetry:
    logging:
      console:
        level: DEBUG  # Shows each step with timestamp
```

**Q: How do I clear old traces?**  
A: Delete the file:
```bash
rm pynemo_engineer_traces.jsonl
```

Or change mode to overwrite:
```yaml
tracing:
  trace_file:
    mode: overwrite  # Changed from append
```

---

## 🏆 Pro Tips

1. **First trace is always slower** - Run twice, analyze the second
2. **Compare apples to apples** - Use the same question when testing configs  
3. **Start with bigger changes** - Switching models > tweaking temperature
4. **Monitor token usage** - Traces show tokens used per LLM call
5. **Profile in production mode** - Use `nat serve` for realistic timing

---

## 📚 Full Documentation

- Full guide: [TRACING_GUIDE.md](./TRACING_GUIDE.md)
- NAT observability docs: [observe.md](../../docs/source/run-workflows/observe/observe.md)
- Profiler docs: [profiler.md](../../docs/source/improve-workflows/profiler.md)

