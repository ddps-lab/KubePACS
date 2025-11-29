# KubeCaps IaC with Custom Karpenter

이 디렉토리는 KubeCaps 프로젝트의 Terraform Infrastructure as Code (IaC)와 커스터마이징된 Karpenter 구현을 포함합니다.

## 📋 개요

KubeCaps는 비용 효율적이고 고가용성을 제공하며 성능이 우수한 스팟 인스턴스를 사용하는 Kubernetes 클러스터 자동 확장 시스템입니다. 이 프로젝트는 Karpenter를 기반으로 Python 기반의 최적화 알고리즘을 통합하여 스팟 인스턴스 선택을 개선합니다.

## 🏗️ 기술 아키텍처 (Technical Architecture)

KubeCaps는 Karpenter의 확장성과 유연성을 활용하여 커스텀 노드 선택 로직을 통합했습니다. 이 섹션에서는 프로젝트 구조의 기술적 배경과 구현 상세를 설명합니다.

### 1. 프로젝트 구조 분리 배경 (`core` vs `fork`)

Karpenter 프로젝트는 원래 클라우드 제공자(AWS, Azure 등)에 구애받지 않는 핵심 로직(`karpenter-core`)과 각 클라우드 제공자별 구현체(`karpenter-provider-aws` 등)로 나뉘어 있었습니다. KubeCaps는 이 구조를 활용하여 다음과 같이 구성되었습니다:

- **`karpenter-core`**: 
  - **역할**: Karpenter의 핵심 스케줄링 로직, API 정의, 메트릭 처리 등을 담당합니다.
  - **수정 사항**: 스케줄링 파이프라인(`pkg/controllers/provisioning/scheduling`)에 Python 기반의 외부 솔버를 호출하는 로직(`scheduler_python.go`)이 추가되었습니다. 이는 클라우드 제공자에 종속되지 않는 일반적인 스케줄링 인터페이스를 유지하면서, 내부적으로는 AWS 스팟 가격 데이터를 활용하는 하이브리드 접근 방식을 취합니다.

- **`karpenter-fork`**: 
  - **역할**: AWS Cloud Provider 구현체입니다. 실제 EC2 인스턴스 생성, 삭제, AWS API 통신을 담당합니다.
  - **수정 사항**: `karpenter-core`의 수정된 버전을 import하여 사용하도록 `go.mod`가 조정되어 있으며, Docker 빌드 시 이 포크된 버전을 기반으로 컨트롤러 바이너리를 생성합니다.

이러한 분리 구조는 Karpenter의 업스트림 변경 사항을 추적하면서도, 핵심 스케줄링 로직에만 집중적으로 커스터마이징을 적용하기 위함입니다.

### 2. Python 통합 및 스케줄링 로직

Karpenter의 Go 기반 스케줄러와 Python 최적화 알고리즘의 통합은 다음과 같은 흐름으로 동작합니다:

#### A. 통합 포인트 (`scheduler.go`)

`karpenter-core/pkg/controllers/provisioning/scheduling/scheduler.go`의 `Solve` 함수에 훅(Hook)이 추가되었습니다.

```go
// scheduler.go
func (s *Scheduler) Solve(ctx context.Context, pods []*corev1.Pod) (Results, error) {
    // ...
    // 1. 전략 어노테이션 확인
    usePython := false
    for _, nct := range s.nodeClaimTemplates {
        if val, ok := nct.Annotations["kubepacs.io/strategy"]; ok && val == "kubepacs" {
            usePython = true
            break
        }
    }

    // 2. Python 솔버 실행
    if usePython && len(pods) > 0 {
        results, err := s.solvePython(ctx, pods)
        if err == nil {
            return results, nil // 성공 시 커스텀 결과 반환
        }
        // 실패 시 기본 로직으로 폴백(Fallback)
    }
    // ... 기본 Karpenter 스케줄링 로직
}
```

#### B. 데이터 교환 프로세스 (`scheduler_python.go`)

1. **입력 데이터 준비**:
   - 대기 중인 Pod들의 평균 CPU/Memory 요구량을 계산합니다.
   - NodeClaimTemplate에서 사용 가능한 인스턴스 타입 목록을 필터링하여 JSON 파일로 저장합니다.
   
2. **Python 스크립트 실행**:
   - `exec.Command`를 사용하여 `/usr/local/bin/kubepacs_cli.py`를 서브프로세스로 실행합니다.
   - 인자로 Pod 수, 리소스 요구량, 리전 정보 등을 전달합니다.

3. **최적화 수행 (Python)**:
   - 실시간 AWS 스팟 가격 데이터를 수집합니다.
   - CoreMark 성능 데이터를 로드합니다.
   - Linear Programming (PuLP)을 사용하여 비용 대비 성능이 최적화된 인스턴스 조합을 계산합니다.

4. **결과 처리 및 노드 생성**:
   - Python 스크립트가 반환한 JSON 결과(인스턴스 타입, AZ, 개수)를 파싱합니다.
   - 이에 맞춰 Karpenter의 `NodeClaim` 객체를 생성하고, Pod를 해당 노드에 할당(Binding)합니다.

### 3. 로직 비교 (Visual Logic)

왜 스케줄러를 수정해야 했는지, 기존 방식과 KubeCaps 방식의 차이를 시각적으로 비교하면 다음과 같습니다.

```mermaid
flowchart TD
    subgraph Vanilla["Vanilla Karpenter (기존)"]
        V_Pod[Pod Pending] --> V_Sched[Scheduler]
        V_Sched --> V_List[AWS Price List]
        V_List --> V_Cand[여러 후보군 추출\n(c5, m5, r5...)]
        V_Cand --> V_AWS[AWS CreateFleet API]
        V_AWS -- "AWS가 결정\n(재고/가격 중심)" --> V_Node[노드 생성]
        V_Node -.-> V_Result[성능 고려 부족\n비효율적일 수 있음]
        style V_Result stroke:#ff9999,stroke-width:2px
    end

    subgraph KubeCaps["KubeCaps (개선)"]
        K_Pod[Pod Pending] --> K_Hook[Scheduler Hook]
        K_Hook --> K_Py[Python Solver]
        
        subgraph Logic["최적화 로직"]
            K_Py -- "실시간 가격" --> K_Algo
            Data[CoreMark\n성능 데이터] --> K_Algo{Linear\nProgramming}
        end
        
        K_Algo --> K_Opt[최적 타입 확정\n(예: c5.2xlarge)]
        K_Opt --> K_AWS[AWS CreateFleet API\n(콕 집어서 요청)]
        K_AWS -- "우리가 결정\n(성능+비용 최적)" --> K_Node[노드 생성]
        K_Node -.-> K_Result[비용 대비\n최고 성능 보장]
        style K_Result stroke:#99ff99,stroke-width:2px
    end
```

**핵심 차이점**:
- **Vanilla**: AWS에게 "적당한 거 주세요"라고 후보군을 던지고, AWS의 처분에 맡깁니다. (수동적)
- **KubeCaps**: 성능 데이터를 기반으로 우리가 "이게 제일 좋습니다"라고 계산한 뒤, AWS에게 "이거 주세요"라고 요구합니다. (능동적)

### 4. 커스텀 Karpenter 구현

KubeCaps는 두 개의 Karpenter 저장소를 사용하여 커스터마이징된 노드 선택 알고리즘을 구현합니다:

1. **karpenter-core**: 핵심 Python 알고리즘 및 데이터
   - `kubepacs_cli.py`: 최적화된 노드 선택 알고리즘
   - `aws_coremark_singlecore.csv`: 인스턴스 성능 데이터

2. **karpenter-fork**: AWS Karpenter 포크
   - Go 기반 컨트롤러
   - Python 알고리즘과 통합

## 🔧 커스텀 Karpenter 빌드 프로세스

### 1. Dockerfile 구조

커스텀 Karpenter 이미지는 멀티스테이지 빌드를 사용합니다:

```dockerfile
# Stage 1: Go 빌드
FROM golang:1.25 AS builder
WORKDIR /src
COPY karpenter-core/ karpenter-core/
COPY karpenter-fork/ karpenter-fork/
WORKDIR /src/karpenter-fork
RUN go mod download
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -a -o controller cmd/controller/main.go

# Stage 2: Python 런타임
FROM python:3.13-slim
WORKDIR /
RUN pip install pandas pulp requests boto3 numpy
COPY --from=builder /src/karpenter-fork/controller .
COPY karpenter-core/pkg/controllers/provisioning/scheduling/kubepacs_cli.py /usr/local/bin/kubepacs_cli.py
COPY karpenter-core/pkg/controllers/provisioning/scheduling/aws_coremark_singlecore.csv /usr/local/bin/aws_coremark_singlecore.csv
ENTRYPOINT ["/controller"]
```

### 2. 빌드 및 푸시

```bash
# ECR 로그인
aws ecr get-login-password --region ap-northeast-2 | docker login --username AWS --password-stdin 786382940258.dkr.ecr.ap-northeast-2.amazonaws.com

# 이미지 빌드 (KubeCaps 루트 디렉토리에서 실행)
cd /Users/taeyoon/Desktop/KubeCaps
docker build -t karpenter-custom -f karpenter-fork/Dockerfile .

# 태그 및 푸시
docker tag karpenter-custom:latest 786382940258.dkr.ecr.ap-northeast-2.amazonaws.com/karpenter-custom:latest
docker push 786382940258.dkr.ecr.ap-northeast-2.amazonaws.com/karpenter-custom:latest
```

## 📊 Python 기반 노드 선택 알고리즘

### 주요 기능

`kubepacs_cli.py`는 다음 기능을 제공합니다:

1. **스팟 가격 수집**: AWS 스팟 인스턴스 가격을 실시간으로 가져옴
2. **성능 데이터 통합**: CoreMark 점수를 기반으로 인스턴스 성능 평가
3. **제약 조건 기반 최적화**: Linear Programming을 사용한 최적 인스턴스 조합 계산
4. **Golden Section Search**: 비용과 성능의 최적 균형점 탐색

### 알고리즘 입력

```bash
python kubepacs_cli.py \
  --pod-count 10 \
  --pod-cpu 1.0 \
  --pod-mem 2.0 \
  --region ap-northeast-2 \
  --allowed-instances-file /path/to/allowed.json
```

### 출력 형식

```json
[
  {
    "instance_type": "c5.xlarge",
    "availability_zone": "ap-northeast-2a",
    "num_instances": 2
  },
  {
    "instance_type": "c5.2xlarge",
    "availability_zone": "ap-northeast-2c",
    "num_instances": 1
  }
]
```

## 🚀 배포 가이드

### 사전 요구사항

- AWS CLI 설정 완료
- Terraform v1.0 이상
- Docker
- kubectl

### 1. 환경 변수 설정

`.env` 파일을 생성하고 필요한 값을 설정합니다:

```bash
AWS_REGION=ap-northeast-2
AWS_ACCOUNT_ID=786382940258
PREFIX=kubepacs-t1
```

### 2. Terraform 변수 설정

`var.tf`를 확인하고 필요한 변수를 설정합니다:

```hcl
variable "prefix" {
  description = "Prefix for resource names"
  type        = string
  default     = "kubepacs-t1"
}
```

### 3. 인프라 배포

```bash
cd IaC_karpenter_kubepacs

# Terraform 초기화
terraform init

# 계획 확인
terraform plan

# 인프라 배포
terraform apply --auto-approve
```

### 4. 커스텀 Karpenter 이미지 빌드 및 푸시

```bash
# KubeCaps 루트로 이동
cd /Users/taeyoon/Desktop/KubeCaps

# ECR 로그인
aws ecr get-login-password --region ap-northeast-2 | \
  docker login --username AWS --password-stdin \
  786382940258.dkr.ecr.ap-northeast-2.amazonaws.com

# 빌드
docker build -t karpenter-custom -f karpenter-fork/Dockerfile .

# 푸시
docker tag karpenter-custom:latest \
  786382940258.dkr.ecr.ap-northeast-2.amazonaws.com/karpenter-custom:latest
docker push 786382940258.dkr.ecr.ap-northeast-2.amazonaws.com/karpenter-custom:latest
```

### 5. kubeconfig 설정

```bash
aws eks update-kubeconfig \
  --region ap-northeast-2 \
  --name kubepacs-t1-k8s-cluster
```

### 6. Karpenter 검증

```bash
# NodePool 및 테스트 Deployment 배포
kubectl apply -f verification.yaml

# Karpenter 로그 확인
kubectl logs -n kube-system -l app.kubernetes.io/name=karpenter -f

# 노드 생성 확인
kubectl get nodes

# Pod 상태 확인
kubectl get pods
```

## 📝 주요 설정

### EKS 클러스터

- **버전**: 1.33
- **엔드포인트**: 퍼블릭 액세스 활성화
- **NodeGroup**: `kubepacs_addon_nodes` (Bottlerocket AMI, 스팟 인스턴스)

### ECR 리포지토리

- **이름**: `karpenter-custom`
- **변경 가능성**: MUTABLE
- **강제 삭제**: `force_delete = true` (이미지가 있어도 삭제 가능)
- **이미지 스캔**: 푸시 시 자동 스캔

### Karpenter NodePool 어노테이션

```yaml
metadata:
  name: default
  annotations:
    kubepacs.io/strategy: kubepacs  # 커스텀 전략 활성화
```

## 🧪 검증 (verification.yaml)

### 구성 요소

1. **EC2NodeClass**: AL2023 AMI, Karpenter 노드용 IAM 역할/보안그룹
2. **NodePool**: 
   - 스팟 인스턴스만 사용
   - AMD64 아키텍처
   - `kubepacs.io/strategy: kubepacs` 어노테이션으로 커스텀 알고리즘 활성화
3. **Test Deployment**: 
   - 5개의 replica
   - 각 Pod당 1 CPU, 1Gi 메모리 요청

## 🔄 인프라 업데이트

### 변경 사항 적용

```bash
terraform plan
terraform apply
```

### 리소스 삭제

```bash
# 먼저 Kubernetes 리소스 삭제
kubectl delete -f verification.yaml

# Terraform 리소스 삭제
terraform destroy
```

**참고**: ECR 리포지토리는 `force_delete = true` 설정으로 이미지가 있어도 자동 삭제됩니다.

## 📌 중요 사항

### 네이밍 일관성

프로젝트 전체에서 `kubepacs` 네이밍을 사용합니다:
- NodeGroup: `kubepacs_addon_nodes`
- 접두사: `kubepacs-t1`
- 전략 어노테이션: `kubepacs.io/strategy`

### 리전 설정

현재 설정: `ap-northeast-2` (서울)

다른 리전을 사용하려면:
1. `var.tf`의 리전 변수 수정
2. `kubepacs_cli.py` 호출 시 `--region` 파라미터 업데이트
3. ECR 로그인 및 푸시 명령의 리전 변경

## 🛠️ 트러블슈팅

### ECR 리포지토리 삭제 오류

**문제**: `RepositoryNotEmptyException: The repository still contains images`

**해결**:
```bash
# 수동으로 이미지 삭제
aws ecr batch-delete-image \
  --repository-name karpenter-custom \
  --region ap-northeast-2 \
  --image-ids imageDigest=<digest>

# 또는 ecr.tf에 force_delete = true 추가 (이미 설정됨)
```

### Terraform 경고

현재 알려진 경고:
- Provider 버전 제약 조건 위치 (deprecated)
- 정의되지 않은 provider 참조

이러한 경고는 기능에 영향을 주지 않지만, 향후 Terraform 버전에서 수정이 필요할 수 있습니다.

## 📚 참고 자료

- [Karpenter 공식 문서](https://karpenter.sh/)
- [AWS EKS 모듈](https://registry.terraform.io/modules/terraform-aws-modules/eks/aws/latest)
- [PuLP 최적화 라이브러리](https://coin-or.github.io/pulp/)

## 📄 라이선스

이 프로젝트는 개별 컴포넌트의 라이선스를 따릅니다:
- Karpenter: Apache License 2.0
- 기타 오픈소스 라이브러리: 각 라이브러리의 라이선스 참조
