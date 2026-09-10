FROM --platform=linux/arm64 public.ecr.aws/lambda/python:3.12

COPY requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

COPY lambda_kubepacs_api.py ${LAMBDA_TASK_ROOT}/
COPY aws_coremark_singlecore.csv ${LAMBDA_TASK_ROOT}/
COPY data ${LAMBDA_TASK_ROOT}/data

CMD ["lambda_kubepacs_api.lambda_handler"]
