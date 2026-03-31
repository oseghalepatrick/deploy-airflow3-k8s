# Export values for Airflow docker image
export REGION=eu-west-1
export ECR_REGISTRY=722741357404.dkr.ecr.eu-west-1.amazonaws.com
export ECR_REPO=my-dags
export NAMESPACE=airflow
export RELEASE_NAME=airflow

# Authenticate with ECR
aws --profile patrick2 ecr get-login-password --region $REGION \
    | docker login --username AWS --password-stdin $ECR_REGISTRY

# Get the latest image tag from ECR
export IMAGE_TAG=$(
    aws --profile patrick2 ecr list-images \
    --repository-name my-dags \
    --region eu-west-1 \
    --query 'imageIds[*].imageTag' \
    --output text \
    | tr '\t' '\n' \
    | sort -r \
    | head -n 1
)

# Load the image into kind
docker pull $ECR_REGISTRY/$ECR_REPO:$IMAGE_TAG
kind load docker-image $ECR_REGISTRY/$ECR_REPO:$IMAGE_TAG

# Apply kubernetes secrets
kubectl apply -f k8s/secrets/git-secrets.yaml

kubectl apply -f k8s/volumes/airflow-logs-pv.yaml
kubectl apply -f k8s/volumes/airflow-logs-pvc.yaml

# Upgrade Airflow using Helm
helm upgrade $RELEASE_NAME apache-airflow/airflow \
    --namespace $NAMESPACE -f chart/values-override-persistence.yaml \
    --set-string images.airflow.repository=$ECR_REGISTRY/$ECR_REPO \
    --set-string images.airflow.tag="$IMAGE_TAG" \
    --debug

# Port forward the API server
kubectl port-forward svc/$RELEASE_NAME-api-server 8080:8080 --namespace $NAMESPACE
