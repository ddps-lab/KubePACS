# KubePACS API

The Lambda handler runs the optimizer against packaged price data. It does not
provision instances. Commands below start at the repository root.

## Requirements

Use Python 3.11 for the local check, uv, and AWS credentials with
`ec2:DescribeInstanceTypes` and `ec2:DescribeAvailabilityZones` permissions.
The price input is local, but AWS metadata requests still require connectivity.
The Lambda image uses Python 3.12 on ARM64; a local smoke test does not validate
that image or its bundled CBC solver on ARM64.

## Local Functional Check

```sh
uv venv --python 3.11 api/.venv
uv pip install --python api/.venv/bin/python -r api/requirements.txt boto3==1.42.97
export AWS_PROFILE=default
api/.venv/bin/python - <<'PY'
import json
from api.lambda_kubepacs_api import lambda_handler

assert lambda_handler({}, None)["statusCode"] == 400
response = lambda_handler({
    "pod_count": 10, "pod_cpu": 0.5, "pod_mem": 1.0, "region": "us-east-1"
}, None)
print(json.dumps(response, indent=2))
assert response["statusCode"] == 200, response
nodes = json.loads(response["body"])["result"]
assert nodes
assert all(n["instance_type"] and n["availability_zone"]
           and n["num_instances"] > 0 for n in nodes)
print("PASS: validation and optimizer response")
PY
```

Choose your own configured profile instead of `default` when needed.
Boto3 is installed explicitly for local execution; Lambda supplies it in its
runtime. The other versions are pinned in `requirements.txt`.

Success is exit code 0, status 200, and a nonempty node allocation. This smoke
test checks the response contract, not global optimality, schedulability with
Kubernetes overhead, or historical paper results. Selected instances can vary
with AWS metadata and account-specific AZ mappings. Retain stdout, the source
revision, dependency versions, and input checksum with evaluation results.

## Request Contract

The handler accepts a direct dictionary or a Function URL event whose `body`
is a JSON string.

| Field | Required | Meaning |
| --- | --- | --- |
| `pod_count` | Yes | Positive integer pod count |
| `pod_cpu` | Yes | Positive vCPU request per pod |
| `pod_mem` | Yes | Positive GiB request per pod |
| `region` | Yes | AWS region, e.g. `us-east-1` |
| `workload_intensity` | No | `default`, `network`, `disk`, or `disk_network` |
| `allowed_instances` | No | Array of `{"instance_type": "...", "availability_zone": "..."}` candidates |
| `spot_data_path` | No | Local JSON or gzip JSON file path |
| `spot_data` | No | Inline SpotLake record array; takes precedence over the file |

The default input is `api/data/latest_aws.json`. A different file can be
selected through `KUBEPACS_SPOT_DATA_PATH` or the request field. A request path
must exist on the machine/container running the handler, not on the client.
Keep the shared CoreMark CSV and data directory beside the handler.

A successful response body has the shape:

```json
{"result": [{"instance_type": "INSTANCE_TYPE", "availability_zone": "AZ", "num_instances": 1}]}
```

Direct invocation wraps this in `statusCode`, headers, and a JSON-string
`body`. Missing/nonpositive required inputs return 400; no feasible solution
returns 404; data-loading failures can return 502; unexpected errors return
500. Inspect logs for the cause of 502, including AWS authorization failures.

## Image And Hosted Endpoint

Build from the repository root:

```sh
docker build --platform linux/arm64 -t kubepacs-api:artifact api
```

This requires Docker with ARM64 build support and internet access. Before
deployment, separately test the image's handler and CBC executable on the
target architecture and configure the Lambda execution role for the read-only
EC2 calls above. Container build and Lambda deployment are not validated by
the local check.

The public endpoint at `https://api.kubepacs.ddps.cloud/` is optional and may
not run the submitted revision. Do not use it as evidence that the local
artifact passes. The local smoke test creates no AWS resources; any separately
deployed Lambda, registry images, and logging resources need separate cleanup.
