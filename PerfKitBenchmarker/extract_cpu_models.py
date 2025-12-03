#!/usr/bin/env python3

import json
import os
import csv
from pathlib import Path

def extract_cpu_info(json_file_path):
    """Extract CPU model information from perfkitbenchmarker_results.json"""
    try:
        # Read file as JSON lines (each line is a separate JSON object)
        with open(json_file_path, 'r') as f:
            lines = f.readlines()
        
        cpu_model = "Not found"
        
        for line in lines:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
                
                # Find the entry with lscpu metric
                if item.get('metric') == 'lscpu':
                    labels = item.get('labels', '')
                    # Parse labels to extract CPU model
                    for label in labels.split('|,|'):
                        if 'Model name:' in label:
                            cpu_model = label.split('Model name:')[1].strip('|')
                            break
                        elif 'model name:' in label:
                            cpu_model = label.split('model name:')[1].strip('|')
                            break
                
                # Alternative: look for cpu_model in labels of any metric
                if cpu_model == "Not found":
                    labels = item.get('labels', '')
                    for label in labels.split('|,|'):
                        if 'cpu_model:' in label:
                            cpu_model = label.split('cpu_model:')[1].strip('|')
                            break
            except json.JSONDecodeError:
                continue
                    
        return cpu_model
    except Exception as e:
        return f"Error: {str(e)}"

def extract_coremark_scores(json_file_path):
    """Extract all CoreMark scores from perfkitbenchmarker_results.json"""
    scores = []
    try:
        # Read file as JSON lines (each line is a separate JSON object)
        with open(json_file_path, 'r') as f:
            lines = f.readlines()
        
        for line in lines:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
                
                # Find CoreMark Score entries
                if item.get('metric') == 'Coremark Score':
                    score = item.get('value', 0)
                    if score > 0:
                        scores.append(score)
            except json.JSONDecodeError:
                continue
                    
        return scores
    except Exception as e:
        return []

def main():
    base_dir = Path("/Users/taeyoon/Desktop/KubeCaps/PerfKitBenchmarker/runs")
    results = []
    
    # Iterate through all directories
    for pricing_policy in ['dedicated', 'spot']:
        pricing_dir = base_dir / pricing_policy
        if not pricing_dir.exists():
            continue
            
        for run_num in os.listdir(pricing_dir):
            run_dir = pricing_dir / run_num
            if not run_dir.is_dir():
                continue
                
            for instance_type in os.listdir(run_dir):
                instance_dir = run_dir / instance_type
                if not instance_dir.is_dir():
                    continue
                    
                json_file = instance_dir / "perfkitbenchmarker_results.json"
                if json_file.exists():
                    cpu_model = extract_cpu_info(json_file)
                    coremark_scores = extract_coremark_scores(json_file)
                    avg_coremark = sum(coremark_scores) / len(coremark_scores) if coremark_scores else 0
                    
                    result = {
                        'pricing_policy': pricing_policy,
                        'run_number': run_num,
                        'instance_type': instance_type,
                        'cpu_model': cpu_model,
                        'avg_coremark': round(avg_coremark, 2)
                    }
                    
                    # Add individual scores
                    for i in range(5):
                        if i < len(coremark_scores):
                            result[f'score_{i+1}'] = round(coremark_scores[i], 2)
                        else:
                            result[f'score_{i+1}'] = None
                    
                    results.append(result)
                    
                    # Print with individual scores
                    scores_str = " | ".join([f"{s:.2f}" if s else "N/A" for s in [result.get(f'score_{i+1}') for i in range(5)]])
                    print(f"{pricing_policy:10} | Run {run_num} | {instance_type:10} | Avg: {avg_coremark:8,.2f} | Scores: {scores_str}")
    
    # Save to CSV
    csv_file = base_dir.parent / "cpu_models.csv"
    fieldnames = ['pricing_policy', 'run_number', 'instance_type', 'cpu_model', 'avg_coremark', 
                  'score_1', 'score_2', 'score_3', 'score_4', 'score_5']
    with open(csv_file, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)
    
    print(f"\nResults saved to: {csv_file}")
    
    # Print summary
    print("\n=== CPU Model and CoreMark Summary by Instance Type ===")
    summary = {}
    for result in results:
        key = f"{result['instance_type']} ({result['pricing_policy']})"
        if key not in summary:
            summary[key] = {'cpu_models': set(), 'coremarks': []}
        summary[key]['cpu_models'].add(result['cpu_model'])
        summary[key]['coremarks'].append(result['avg_coremark'])
    
    for instance_type, data in sorted(summary.items()):
        avg_score = sum(data['coremarks']) / len(data['coremarks']) if data['coremarks'] else 0
        print(f"\n{instance_type}:")
        for cpu in data['cpu_models']:
            print(f"  CPU: {cpu}")
        print(f"  Avg CoreMark across runs: {avg_score:,.2f}")

if __name__ == "__main__":
    main()