#!/bin/bash

# 인스턴스 타입 리스트
machine_types=("m5.12xlarge" "m5.16xlarge" "m5.24xlarge" "m5.2xlarge" "m5.4xlarge" "m5.8xlarge" "m5.large" "m5.xlarge")

# S3 버킷 이름
s3_bucket="s3://2025-coremark"

# 타임스탬프
timestamp=$(date "+%Y%m%d-%H%M%S")

# 루트 디렉토리
base_output_dir="./coremark_results"
mkdir -p "$base_output_dir"

for machine_type in "${machine_types[@]}"; do
    (
        # run_uri 설정
        run_uri="${machine_type//./}"  # 점(.) 제거
        run_uri="${run_uri//-/}"    # 하이픈(-) 제거

        # 작업 디렉토리
        output_dir="${base_output_dir}/${run_uri}"
        mkdir -p "$output_dir"
        cd "$output_dir" || exit 1

        echo "[INFO] Starting benchmark for $machine_type (run_uri=$run_uri)"

        # PKB 실행
        python3.11 ../../pkb.py \
            --accept_licenses \
            --cloud=AWS \
            --benchmarks=coremark \
            --machine_type="$machine_type" \
            --os_type=ubuntu2404 \
            --coremark_thread_counts=1 \
            --run_stage_iterations=5 \
            --aws_spot_instances=true \
            --zones=us-east-1a \
            --run_uri="$run_uri" > run.log 2>&1
        
        # Check completion status before uploading
        status_file="/tmp/perfkitbenchmarker/runs/${run_uri}/completion_statuses.json"
        failure_log="failures.log" # Log failures in the base directory

        status=""
        # Check if jq is installed and the status file exists
        if command -v jq &> /dev/null && [[ -f "$status_file" ]]; then
            # Attempt to parse the status using jq
            status=$(jq -r '.status' "$status_file")
            # Check if jq command was successful
            if [[ $? -ne 0 ]]; then
                echo "[ERROR] Failed to parse $status_file for $machine_type. Skipping upload."
                # Log the failure reason
                echo "$(date '+%Y-%m-%d %H:%M:%S') - Failed: machine_type=$machine_type, run_uri=$run_uri, reason=json_parse_error" >> "$failure_log"
                exit 1 # Exit subshell on error
            fi
        elif [[ ! -f "$status_file" ]]; then
            # Status file does not exist
            echo "[ERROR] Status file $status_file not found for $machine_type. Skipping upload."
            echo "$(date '+%Y-%m-%d %H:%M:%S') - Failed: machine_type=$machine_type, run_uri=$run_uri, reason=status_file_not_found" >> "$failure_log"
            exit 1 # Exit subshell on error
        else
            # jq command is not available
            echo "[ERROR] 'jq' command not found. Cannot check benchmark status. Skipping upload for $machine_type."
            echo "$(date '+%Y-%m-%d %H:%M:%S') - Failed: machine_type=$machine_type, run_uri=$run_uri, reason=jq_not_found" >> "$failure_log"
            exit 1 # Exit subshell on error
        fi

        # Check if the extracted status is SUCCEEDED
        if [[ "$status" != "SUCCEEDED" ]]; then
            echo "[ERROR] Benchmark for $machine_type did not succeed (status: $status). Skipping upload."
            # Log the failure with the actual status
            echo "$(date '+%Y-%m-%d %H:%M:%S') - Failed: machine_type=$machine_type, run_uri=$run_uri, status=$status" >> "$failure_log"
            exit 1 # Exit subshell if status is not SUCCEEDED
        fi

        # If the script reaches here, the status is SUCCEEDED
        echo "[INFO] Benchmark for $machine_type succeeded. Proceeding with upload."
        # S3 업로드
        s3_path="${s3_bucket}/${machine_type}"
        echo "[INFO] Uploading results to $s3_path"
        aws s3 cp /tmp/perfkitbenchmarker/runs/"$run_uri" "$s3_path" --recursive

        echo "[DONE] $machine_type benchmark and upload complete."
    ) &
done

wait
echo "[ALL DONE] 모든 벤치마크 및 업로드 완료!"
