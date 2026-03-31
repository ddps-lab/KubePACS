# KubePACS API

This API implements the optimization functionality of KubePACS.

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
``'
