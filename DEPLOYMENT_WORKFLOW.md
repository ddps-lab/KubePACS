# KubeCaps Deployment Workflow

이 문서는 KubeCaps Custom Karpenter를 수정하고 클러스터에 배포하는 전체 과정을 정리합니다.

## 1. 코드 수정 (Modify)
`karpenter-core` 또는 `karpenter-fork` 내의 코드를 수정합니다.
- Python 알고리즘: `karpenter-core/pkg/controllers/provisioning/scheduling/kubepacs_cli.py`
- Go 컨트롤러 로직: `karpenter-fork/...`

## 2. 빌드 및 푸시 (Build & Push)
`karpenter-provider-aws` 디렉토리의 스크립트를 사용하여 이미지를 빌드하고 ECR에 푸시합니다.

```bash
cd karpenter_fork/karpenter-provider-aws
./build_and_push.sh
```
* **참고**: 이 스크립트는 `v20` 태그로 이미지를 푸시합니다.

## 3. 클러스터 배포 (Deploy)
새로 빌드된 이미지를 클러스터에 적용하고 Karpenter를 재시작합니다.
새로 생성한 `deploy_and_verify.sh` 스크립트를 사용하세요.

```bash
cd karpenter_fork/karpenter-provider-aws
./deploy_and_verify.sh [TAG]
```
* **TAG**: 생략 시 기본값 `v20`을 사용합니다.
* 이 스크립트는 자동으로 `v20` 이미지를 사용하도록 Deployment를 업데이트하고 롤아웃을 재시작합니다.

## 4. 검증 (Verify)
배포가 완료되면 로그를 확인하여 정상 동작하는지 확인합니다.

```bash
# 로그 스트리밍 확인
kubectl logs -f -n karpenter -l app.kubernetes.io/name=karpenter
```

### 테스트 워크로드 실행
실제 노드 프로비저닝을 테스트하려면 `IaC/IaC_karpenter_kubepacs/verification.yaml`을 사용하세요.

```bash
cd IaC/IaC_karpenter_kubepacs
kubectl apply -f verification.yaml
```

## 작업 흐름 요약
```bash
# 1. 빌드
cd karpenter_fork/karpenter-provider-aws
./build_and_push.sh

# 2. 배포
./deploy_and_verify.sh

# 3. 로그 확인
kubectl logs -f -n karpenter -l app.kubernetes.io/name=karpenter
```
