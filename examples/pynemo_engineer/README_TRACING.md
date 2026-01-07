# Performance Tracing Setup Complete! ✅

Your PyNemo Engineer workflow now has **built-in performance tracing** to identify bottlenecks.

## 🚀 How to Use

### 1. Run your workflow (tracing is automatic)
```bash
cd examples/pynemo_engineer
nat run --config_file configs/config.yaml --input "What is DoMINO?"
```

### 2. Analyze the performance
```bash
python scripts/analyze_traces.py
```

That's it! You'll see:
- ⏱️ **Total execution time**
- 🤖 **LLM call breakdown** (usually the bottleneck)
- 🔧 **Tool execution times**
- 📚 **Retriever performance**
- 💡 **Optimization recommendations**

## 📊 What Changed in Your Config

Added this section to `configs/config.yaml`:

```yaml
general:
  telemetry:
    logging:
      console:
        _type: console
        level: INFO
    tracing:
      trace_file:
        _type: file
        output_path: pynemo_engineer_traces.jsonl
        project: pynemo_engineer
        mode: append
```

## 🎯 Expected Results

Based on your config, you're likely to see:

```
🤖 LLM CALLS (Potential Bottleneck)
Total LLM calls: 6-10
Total LLM time: 30-50 seconds
Percentage of total time: 75-90%

💡 RECOMMENDATIONS
⚠️  LLM calls account for >70% of execution time
```

**This is normal!** Your current model (`deepseek-ai/deepseek-v3.2`) is powerful but slow.

## ⚡ Quick Optimization

To make it **3x faster**, change the model in `config.yaml`:

```yaml
llms:
  nim_llm:
    model_name: meta/llama-3.3-70b-instruct  # Much faster!
    temperature: 0.6
    max_tokens: 16384
```

## 📚 Documentation

- **Quick Reference**: [QUICK_TRACE_REFERENCE.md](./QUICK_TRACE_REFERENCE.md) - Fast tips and common fixes
- **Full Guide**: [TRACING_GUIDE.md](./TRACING_GUIDE.md) - Comprehensive documentation
- **Analysis Script**: `scripts/analyze_traces.py` - The tool that analyzes traces

## 🔍 Files Created

1. **Modified**: `configs/config.yaml` - Added tracing configuration
2. **New**: `scripts/analyze_traces.py` - Performance analysis tool
3. **New**: `TRACING_GUIDE.md` - Full documentation
4. **New**: `QUICK_TRACE_REFERENCE.md` - Quick tips
5. **New**: `README_TRACING.md` - This file

## 🎨 Want a Visual UI?

For a web-based trace viewer with timelines and graphs:

```bash
# Install Phoenix
uv pip install -e '.[phoenix]'
uv pip install arize-phoenix

# Start server
phoenix serve

# Update config (see TRACING_GUIDE.md)
# Then view at: http://localhost:6006
```

## ❓ Common Questions

**Q: Where is the trace file?**  
A: `pynemo_engineer_traces.jsonl` in the current directory

**Q: Can I see timing in real-time?**  
A: Yes! Change `level: INFO` to `level: DEBUG` in the config

**Q: How do I compare different configurations?**  
A: Run with different configs, rename trace files, analyze each:
```bash
python scripts/analyze_traces.py traces_config1.jsonl
python scripts/analyze_traces.py traces_config2.jsonl
```

**Q: The trace file is getting huge!**  
A: Change `mode: append` to `mode: overwrite` in the config

## 🏁 Next Steps

1. ✅ Run your workflow to generate traces
2. ✅ Analyze with `python scripts/analyze_traces.py`
3. ✅ Check if LLM is the bottleneck (it probably is)
4. ✅ Try a faster model if needed
5. ✅ Re-run and compare results

Happy optimizing! 🚀

