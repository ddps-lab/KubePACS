import json
import polars as pl
from pathlib import Path

def extract_coremark_scores():
    results = []
    
    # Define the base runs directory
    runs_dir = Path("runs")
    
    # Instance types to search for
    instance_types = ["c7ilarge", "i7ilarge", "m7ilarge", "r7ilarge", "t3micro"]
    
    # Search for all perfkitbenchmarker_results.json files
    for json_file in runs_dir.rglob("perfkitbenchmarker_results.json"):
        print(json_file)
        # Parse the path to extract information
        parts = json_file.parts
        
        # Skip if path doesn't match expected structure
        if len(parts) < 4:
            continue
            
        # Extract path components
        allocation_type = parts[1]  # dedicated or spot
        
        # Extract run number if present
        run_number = None
        instance_folder_idx = -2  # Second to last should be instance type
        
        # Check if there's a run number (1, 2, or 3)
        for i, part in enumerate(parts):
            if part in ["1", "2", "3"]:
                run_number = part
                instance_folder_idx = i + 1
                break
        
        # Get instance type from folder name
        if instance_folder_idx < len(parts):
            instance_type = parts[instance_folder_idx]
        else:
            instance_type = parts[-2]  # Fallback to second-to-last
            
        # Read and parse JSON file
        try:
            with open(json_file, 'r') as f:
                # JSON file contains one JSON object per line
                for line in f:
                    try:
                        data = json.loads(line.strip())
                        if data.get("metric") == "Coremark Score":
                            results.append({
                                "allocation_type": allocation_type,
                                "run_number": run_number if run_number else "N/A",
                                "instance_type": instance_type,
                                "coremark_score": data.get("value"),
                                "file_path": str(json_file)
                            })
                            break  # Found the score, move to next file
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            print(f"Error reading {json_file}: {e}")
    
    # Create polars DataFrame
    df = pl.DataFrame(results)
    
    # Sort by allocation type, instance type, and run number
    df = df.sort(["allocation_type", "instance_type", "run_number"])
    
    return df

# Run the extraction
df = extract_coremark_scores()

# Display the DataFrame
print("Coremark Scores by Instance Type and Allocation Type:")
print("=" * 80)
print(df)

# Show summary statistics grouped by instance type and allocation type
print("\n\nSummary Statistics:")
print("=" * 80)

# Group by allocation type and instance type to show average scores
summary = df.group_by(["allocation_type", "instance_type"]).agg([
    pl.col("coremark_score").mean().alias("avg_score"),
    pl.col("coremark_score").std().alias("std_dev"),
    pl.col("coremark_score").min().alias("min_score"),
    pl.col("coremark_score").max().alias("max_score"),
    pl.col("coremark_score").count().alias("count")
]).sort(["allocation_type", "instance_type"])

print(summary)

# Create a pivot table for easier comparison
print("\n\nPivot Table - Average Coremark Scores:")
print("=" * 80)

pivot = df.group_by(["instance_type", "allocation_type"]).agg(
    pl.col("coremark_score").mean()
).pivot(
    on="allocation_type",
    index="instance_type",
    values="coremark_score"
)

print(pivot)

# Save results to CSV
df.write_csv("coremark_scores.csv")
print("\n\nResults saved to coremark_scores.csv")