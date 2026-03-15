# KubePACS API

KubePACS ILP solver deployed as an AWS Lambda container (arm64) behind CloudFront.

**Endpoint:** `https://api.kubepacs.ddps.cloud/`

## Request

`POST` with JSON body:

| Parameter | Type | Required | Description |
|---|---|---|---|
| `pod_count` | int | Yes | Number of pods to schedule |
| `pod_cpu` | float | Yes | CPU request per pod (vCPU) |
| `pod_mem` | float | Yes | Memory request per pod (GiB) |
| `region` | string | Yes | AWS region (e.g. `us-east-1`) |
| `workload_intensity` | string | No | `"default"`, `"network"`, `"disk"`, or `"disk_network"`. Defaults to `"default"` |
| `allowed_instances` | list | No | List of `{"instance_type": "...", "availability_zone": "..."}` to restrict candidates |

## Example

```bash
curl -X POST "https://api.kubepacs.ddps.cloud/" \
  -H "Content-Type: application/json" \
  -d '{
    "pod_count": 10,
    "pod_cpu": 0.5,
    "pod_mem": 1.0,
    "region": "us-east-1"
  }'
```

### Response

```json
{
  "result": [
    {
      "instance_type": "c8i-flex.xlarge",
      "availability_zone": "us-east-1f",
      "num_instances": 2
    }
  ]
}
```

## Deployment

```bash
# Build & push
cd api
docker build --platform linux/arm64 -t api.kubepacs.ddps.cloud .
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 786382940258.dkr.ecr.us-east-1.amazonaws.com
docker tag api.kubepacs.ddps.cloud:latest 786382940258.dkr.ecr.us-east-1.amazonaws.com/api.kubepacs.ddps.cloud:latest
docker push 786382940258.dkr.ecr.us-east-1.amazonaws.com/api.kubepacs.ddps.cloud:latest

# Update Lambda
aws lambda update-function-code \
  --function-name api-kubepacs-ddps-cloud \
  --image-uri 786382940258.dkr.ecr.us-east-1.amazonaws.com/api.kubepacs.ddps.cloud:latest \
  --region us-east-1
```
