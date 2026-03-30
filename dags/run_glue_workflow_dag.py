from datetime import datetime

from airflow.sdk import dag
from airflow.providers.amazon.aws.transfers.local_to_s3 import LocalFilesystemToS3Operator
from airflow.providers.amazon.aws.operators.glue import GlueJobOperator

from produce_data import posts_asset, users_asset

AWS_CONN_ID = "aws_conn"
AWS_REGION = "eu-west-1"

S3_BUCKET = "stackexchange-data-platform-joy"
LOCAL_GLUE_SCRIPT = "/opt/airflow/dags/src/scripts/my_etl.py"
S3_GLUE_SCRIPT_KEY = "scripts/my_etl.py"
S3_GLUE_SCRIPT_PATH = f"s3://{S3_BUCKET}/{S3_GLUE_SCRIPT_KEY}"

@dag(
    dag_id="run_aws_glue_job",
    start_date=datetime(2026, 3, 30),
    schedule=(posts_asset & users_asset),
    catchup=False,
    tags=["aws", "glue", "s3"],
)
def upload_and_run_aws_glue_job():

    upload_glue_script = LocalFilesystemToS3Operator(
        task_id="upload_glue_script",
        filename=LOCAL_GLUE_SCRIPT,
        dest_bucket=S3_BUCKET,
        dest_key=S3_GLUE_SCRIPT_KEY,
        aws_conn_id=AWS_CONN_ID,
        replace=True,
    )

    run_glue_job = GlueJobOperator(
        task_id="run_glue_job",
        job_name="test-job",
        script_location=S3_GLUE_SCRIPT_PATH,
        iam_role_name="GlueNotebookTutorialRole",
        region_name=AWS_REGION,
        s3_bucket=S3_BUCKET,
        aws_conn_id=AWS_CONN_ID,
        wait_for_completion=True,
        verbose=True,
        script_args={
            "--input_path": f"s3://{S3_BUCKET}/raw/",
            "--output_path": f"s3://{S3_BUCKET}/processed/",
        },
        create_job_kwargs={
            "GlueVersion": "5.0",
            "NumberOfWorkers": 2,
            "WorkerType": "G.1X",
        },
        run_job_kwargs={
            "Timeout": 60,
        },
    )

    upload_glue_script >> run_glue_job

upload_and_run_aws_glue_job()