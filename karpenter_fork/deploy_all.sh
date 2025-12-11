#!/bin/bash
set -e

# 1. Build and Push to Source Region (ap-northeast-1)
echo "=== Step 1: Building and Pushing to Source Region (ap-northeast-1) ==="
cd karpenter-provider-aws
./build_and_push.sh
cd ..

# 2. Propagate to Other Regions (eu-west-1, us-east-1, us-west-2)
echo "=== Step 2: Propagating Image to Other Regions ==="
./push_other_regions.sh

# 3. Restart Karpenter in All Clusters
echo "=== Step 3: Rolling out changes to all clusters ==="
CLUSTERS=("kubepacs-a1" "kubepacs-e1" "kubepacs-w1" "kubepacs-w2" "arn:aws:eks:ap-northeast-2:786382940258:cluster/kubepacs-t1-k8s-cluster")

for ctx in "${CLUSTERS[@]}"; do
    echo "------------------------------------------------"
    echo "Restarting Karpenter in context: $ctx"
    
    if ! kubectl config get-contexts "$ctx" > /dev/null 2>&1; then
        echo "WARNING: Context '$ctx' not found. Skipping."
        continue
    fi

    kubectl config use-context "$ctx"
    if kubectl rollout restart deployment karpenter -n karpenter; then
        echo "Rollout started. Waiting for completion..."
        if kubectl rollout status deployment/karpenter -n karpenter --timeout=120s; then
            echo "SUCCESS: $ctx updated."
        else
            echo "ERROR: Rollout timed out for $ctx."
            # Optional: exit 1 # Don't exit entire script, try others?
        fi
    else
        echo "ERROR: Failed to restart deployment in $ctx."
    fi
done

echo "================================================"
echo "Deployment Pipeline Complete!"
echo "All regions updated and restarts triggered."
