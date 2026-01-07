#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2024-2025, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Analyze trace files to identify performance bottlenecks in PyNemo Engineer workflow.
"""

import json
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple, Optional


def parse_events_to_spans(events: List[Dict]) -> List[Dict]:
    """
    Parse NAT IntermediateStep events into complete spans (START/END pairs).
    
    Returns list of span dicts with: name, event_type, start_time, end_time, duration_ms, metadata
    """
    # Map UUID to START events
    start_events = {}
    spans = []
    
    for event in events:
        payload = event.get('payload', {})
        event_type = payload.get('event_type', '')
        uuid = payload.get('UUID', '')
        timestamp = payload.get('event_timestamp', 0)
        name = payload.get('name', 'unknown')
        
        # Categorize event types
        if event_type.endswith('_START'):
            # Store START event
            base_type = event_type.replace('_START', '')
            start_events[uuid] = {
                'uuid': uuid,
                'event_type': base_type,
                'name': name,
                'start_time': timestamp,
                'start_payload': payload
            }
        elif event_type.endswith('_END'):
            # Match with START event
            base_type = event_type.replace('_END', '')
            if uuid in start_events:
                start = start_events[uuid]
                duration_ms = (timestamp - start['start_time']) * 1000  # Convert to ms
                
                # Extract metadata
                metadata = payload.get('metadata', {})
                usage_info = payload.get('usage_info', {})
                
                # Extract model name for LLMs
                model_name = None
                if base_type == 'LLM':
                    model_name = start['name']  # LLM name is in the 'name' field
                
                spans.append({
                    'uuid': uuid,
                    'event_type': base_type,
                    'name': name,
                    'model_name': model_name,
                    'start_time': start['start_time'],
                    'end_time': timestamp,
                    'duration_ms': duration_ms,
                    'metadata': metadata,
                    'usage_info': usage_info,
                    'framework': start['start_payload'].get('framework')
                })
                
                # Remove from pending starts
                del start_events[uuid]
    
    return spans


def analyze_traces(trace_file: str = "pynemo_engineer_traces.jsonl") -> None:
    """Analyze trace file and print timing breakdown."""
    
    trace_path = Path(trace_file)
    if not trace_path.exists():
        print(f"❌ Trace file not found: {trace_file}")
        print("   Run your workflow first to generate traces.")
        return
    
    # Read all events (NAT IntermediateStep format)
    events: List[Dict] = []
    line_count = 0
    with open(trace_path, 'r') as f:
        for line in f:
            line_count += 1
            if line.strip():
                try:
                    data = json.loads(line)
                    events.append(data)
                except json.JSONDecodeError as e:
                    print(f"⚠️  Warning: Skipping malformed JSON on line {line_count}: {e}")
                    continue
    
    if not events:
        print(f"❌ No events found in {trace_file}")
        return
    
    print(f"\n✅ Loaded {len(events)} events from {trace_file} ({line_count} lines)")
    
    # Parse events into paired spans (START/END)
    spans = parse_events_to_spans(events)
    
    if not spans:
        print("\n⚠️  No complete spans found (pairs of START/END events)")
        print("   This might happen if the workflow is still running or crashed.")
        return
    
    print(f"✅ Parsed {len(spans)} complete spans\n")
    
    print("\n" + "="*80)
    print("🔍 PYNEMO ENGINEER WORKFLOW - PERFORMANCE ANALYSIS")
    print("="*80 + "\n")
    
    # Group spans by type
    span_types = defaultdict(list)
    llm_calls = []
    tool_calls = []
    retriever_calls = []
    function_calls = []
    workflow_runs = []
    
    for span in spans:
        name = span['name']
        duration_ms = span['duration_ms']
        event_type = span['event_type']
        
        span_types[name].append(duration_ms)
        
        # Categorize spans
        if event_type == 'LLM':
            llm_calls.append(span)
        elif event_type == 'FUNCTION':
            # Check if it's a retriever or tool
            if 'retriever' in name.lower() or 'retrieve' in name.lower():
                retriever_calls.append(span)
            else:
                tool_calls.append(span)
            function_calls.append(span)
        elif event_type == 'WORKFLOW':
            workflow_runs.append(span)
    
    # Print summary statistics
    print("📊 SUMMARY STATISTICS")
    print("-" * 80)
    
    # Calculate total workflow duration
    total_duration = 0
    if workflow_runs:
        # Use the longest workflow run
        total_duration = max(w['duration_ms'] for w in workflow_runs)
    else:
        # Fallback: sum of top-level operations
        total_duration = sum(max(durations) for durations in span_types.values()) if span_types else 0
    
    print(f"Total events: {len(events)}")
    print(f"Complete spans: {len(spans)}")
    print(f"Unique operations: {len(span_types)}")
    if workflow_runs:
        print(f"Workflow runs: {len(workflow_runs)}")
        print(f"Total workflow duration: {total_duration:.2f} ms ({total_duration/1000:.2f} seconds)\n")
    else:
        print(f"Total estimated duration: {total_duration:.2f} ms ({total_duration/1000:.2f} seconds)\n")
    
    # LLM Call Analysis
    if llm_calls:
        print("\n🤖 LLM CALLS (Potential Bottleneck)")
        print("-" * 80)
        total_llm_time = sum(call['duration_ms'] for call in llm_calls)
        
        # Extract token usage
        total_prompt_tokens = 0
        total_completion_tokens = 0
        total_reasoning_tokens = 0
        
        for call in llm_calls:
            usage = call.get('usage_info', {})
            token_usage = usage.get('token_usage', {})
            total_prompt_tokens += token_usage.get('prompt_tokens', 0)
            total_completion_tokens += token_usage.get('completion_tokens', 0)
            total_reasoning_tokens += token_usage.get('reasoning_tokens', 0)
        
        print(f"Total LLM calls: {len(llm_calls)}")
        print(f"Total LLM time: {total_llm_time:.2f} ms ({total_llm_time/1000:.2f} seconds)")
        print(f"Average LLM call: {total_llm_time/len(llm_calls):.2f} ms")
        if total_duration > 0:
            print(f"Percentage of total time: {(total_llm_time/total_duration*100):.1f}%")
        
        if total_prompt_tokens > 0 or total_completion_tokens > 0:
            print(f"\nToken Usage:")
            print(f"  Prompt tokens: {total_prompt_tokens:,}")
            print(f"  Completion tokens: {total_completion_tokens:,}")
            if total_reasoning_tokens > 0:
                print(f"  Reasoning tokens: {total_reasoning_tokens:,}")
            print(f"  Total tokens: {total_prompt_tokens + total_completion_tokens:,}")
        
        # Show slowest LLM calls
        llm_calls_sorted = sorted(llm_calls, key=lambda x: x['duration_ms'], reverse=True)
        print("\n   Slowest LLM Calls:")
        for i, call in enumerate(llm_calls_sorted[:5], 1):
            model = call.get('model_name', call.get('name', 'unknown'))
            framework = call.get('framework', 'unknown')
            print(f"   {i}. {call['duration_ms']:>8.2f} ms - {model} (Framework: {framework})")
    
    # Tool/Function Call Analysis (excluding LLMs and workflows)
    if tool_calls:
        print("\n🔧 TOOL & FUNCTION CALLS")
        print("-" * 80)
        total_tool_time = sum(call['duration_ms'] for call in tool_calls)
        print(f"Total tool/function calls: {len(tool_calls)}")
        print(f"Total time: {total_tool_time:.2f} ms ({total_tool_time/1000:.2f} seconds)")
        print(f"Average call: {total_tool_time/len(tool_calls):.2f} ms")
        if total_duration > 0:
            print(f"Percentage of total time: {(total_tool_time/total_duration*100):.1f}%")
        
        # Group by tool name
        tools_by_name = defaultdict(list)
        for call in tool_calls:
            tools_by_name[call['name']].append(call['duration_ms'])
        
        print("\n   By Tool Type:")
        for tool_name, durations in sorted(tools_by_name.items(), 
                                          key=lambda x: sum(x[1]), 
                                          reverse=True)[:10]:  # Top 10
            total = sum(durations)
            avg = total / len(durations)
            max_dur = max(durations)
            print(f"   • {tool_name[:50]}: {len(durations)} calls, {total:.2f} ms total, {avg:.2f} ms avg, {max_dur:.2f} ms max")
    
    # Retriever Call Analysis
    if retriever_calls:
        print("\n📚 RETRIEVER CALLS")
        print("-" * 80)
        total_retriever_time = sum(call['duration_ms'] for call in retriever_calls)
        print(f"Total retriever calls: {len(retriever_calls)}")
        print(f"Total retriever time: {total_retriever_time:.2f} ms ({total_retriever_time/1000:.2f} seconds)")
        print(f"Average retriever call: {total_retriever_time/len(retriever_calls):.2f} ms")
        if total_duration > 0:
            print(f"Percentage of total time: {(total_retriever_time/total_duration*100):.1f}%")
        
        # Group by retriever name
        retrievers_by_name = defaultdict(list)
        for call in retriever_calls:
            retrievers_by_name[call['name']].append(call['duration_ms'])
        
        if len(retrievers_by_name) > 1:
            print("\n   By Retriever:")
            for ret_name, durations in sorted(retrievers_by_name.items(), 
                                              key=lambda x: sum(x[1]), 
                                              reverse=True):
                total = sum(durations)
                avg = total / len(durations)
                print(f"   • {ret_name}: {len(durations)} calls, {total:.2f} ms total, {avg:.2f} ms avg")
    
    # Detailed breakdown of all span types
    print("\n📋 DETAILED SPAN BREAKDOWN")
    print("-" * 80)
    
    sorted_spans = sorted(span_types.items(), 
                         key=lambda x: sum(x[1]), 
                         reverse=True)
    
    for span_name, durations in sorted_spans[:20]:  # Top 20
        total = sum(durations)
        avg = total / len(durations)
        min_dur = min(durations)
        max_dur = max(durations)
        print(f"{span_name[:60]:<60} | Calls: {len(durations):>3} | "
              f"Total: {total:>8.2f} ms | Avg: {avg:>7.2f} ms | "
              f"Min: {min_dur:>7.2f} ms | Max: {max_dur:>7.2f} ms")
    
    # Recommendations
    print("\n\n💡 RECOMMENDATIONS")
    print("-" * 80)
    
    recommendations = []
    
    if llm_calls and total_duration > 0:
        llm_percentage = (sum(call['duration_ms'] for call in llm_calls) / total_duration * 100)
        if llm_percentage > 70:
            recommendations.append(
                f"⚠️  LLM calls account for {llm_percentage:.1f}% of execution time. Consider:\n"
                "   • Using a faster model (e.g., meta/llama-3.3-70b-instruct instead of deepseek-v3.2)\n"
                "   • Reducing max_tokens to speed up generation\n"
                "   • Using lower temperature (0.1-0.3) for faster, more deterministic responses\n"
                "   • Caching LLM responses for repeated queries"
            )
    
    if retriever_calls:
        avg_retriever = sum(call['duration_ms'] for call in retriever_calls) / len(retriever_calls)
        if avg_retriever > 1000:
            recommendations.append(
                f"⚠️  Retriever calls are slow (avg {avg_retriever:.0f}ms). Consider:\n"
                "   • Reducing top_k in retriever configurations (10 → 5)\n"
                "   • Optimizing Milvus indexes\n"
                "   • Using a faster embedding model"
            )
    
    if len(llm_calls) > 10:
        recommendations.append(
            f"⚠️  Many LLM calls detected ({len(llm_calls)} calls). Consider:\n"
            "   • Reducing parse_agent_response_max_retries (4 → 2)\n"
            "   • Using ReWOO agent instead of ReAct for better efficiency\n"
            "   • Simplifying tool descriptions to reduce reasoning steps\n"
            "   • Removing the reasoning_agent wrapper if not needed"
        )
    
    if not recommendations:
        print("✅ Performance looks good! No major bottlenecks detected.")
    else:
        for rec in recommendations:
            print(rec)
            print()
    
    print("="*80 + "\n")


def main():
    """Main entry point."""
    import sys
    
    trace_file = "pynemo_engineer_traces.jsonl"
    if len(sys.argv) > 1:
        trace_file = sys.argv[1]
    
    analyze_traces(trace_file)


if __name__ == "__main__":
    main()

