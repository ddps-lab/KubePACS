# KubeCAPS: Kubernetes Cluster Using Cost-Efficient, Highly Available, and Performative Spot Instances

KubeCaps는 비용 효율적이고 고가용성을 제공하며 성능이 우수한 스팟 인스턴스를 사용하는 Kubernetes 클러스터 자동 확장 시스템입니다.

## 📁 프로젝트 구조

### IaC (Infrastructure as Code)

- **`IaC/`**: 기본 EKS 클러스터 인프라
- **`IaC_karpenter/`**: Karpenter 통합 인프라 
- **`IaC_karpenter_kubepacs/`**: 커스텀 KubeCaps 알고리즘이 통합된 Karpenter 인프라 ⭐

### Karpenter 커스터마이징

- **`karpenter-core/`**: Python 기반 최적화 알고리즘 및 성능 데이터
- **`karpenter-fork/`**: AWS Karpenter 포크 (커스텀 이미지 빌드용)

자세한 내용은 [IaC_karpenter_kubepacs/README.md](./IaC_karpenter_kubepacs/README.md)를 참조하세요.

## 🚀 빠른 시작

### 커스텀 Karpenter를 사용한 배포

1. **인프라 배포**
   ```bash
   cd IaC_karpenter_kubepacs
   terraform init
   terraform apply --auto-approve
   ```

2. **커스텀 Karpenter 이미지 빌드 및 푸시**
   ```bash
   cd /Users/taeyoon/Desktop/KubeCaps
   
   # ECR 로그인
   aws ecr get-login-password --region ap-northeast-2 | \
     docker login --username AWS --password-stdin \
     <ACCOUNT_ID>.dkr.ecr.ap-northeast-2.amazonaws.com
   
   # 빌드 및 푸시
   docker build -t karpenter-custom -f karpenter-fork/Dockerfile .
   docker tag karpenter-custom:latest <ACCOUNT_ID>.dkr.ecr.ap-northeast-2.amazonaws.com/karpenter-custom:latest
   docker push <ACCOUNT_ID>.dkr.ecr.ap-northeast-2.amazonaws.com/karpenter-custom:latest
   ```

3. **kubeconfig 설정**
   ```bash
   aws eks update-kubeconfig --region ap-northeast-2 --name kubepacs-t1-k8s-cluster
   ```

4. **검증**
   ```bash
   kubectl apply -f IaC_karpenter_kubepacs/verification.yaml
   kubectl get nodes
   ```

## 🔧 환경 설정

프로젝트를 사용하기 전에 다음 파일들을 수정해야 합니다:

- `IaC_karpenter_kubepacs/var.tf`: Terraform 변수 설정
- `.env`: 환경 변수 설정 (.env.example 참조)

## 📊 주요 기능

- **Python 기반 최적화**: Linear Programming을 사용한 최적 스팟 인스턴스 선택
- **비용-성능 균형**: Golden Section Search로 최적의 균형점 탐색
- **실시간 가격 데이터**: AWS 스팟 인스턴스 가격 실시간 수집
- **성능 기반 선택**: CoreMark 점수를 활용한 인스턴스 성능 평가

## Git subtree

```bash
git fetch lithops-upstream
git subtree pull --prefix=lithops lithops-upstream/master --squash -m "Update lithops"
```

## 📚 문서

- [IaC_karpenter_kubepacs 상세 가이드](./IaC_karpenter_kubepacs/README.md)
- [Karpenter 공식 문서](https://karpenter.sh/)

## 📄 라이선스

이 프로젝트는 개별 컴포넌트의 라이선스를 따릅니다.
