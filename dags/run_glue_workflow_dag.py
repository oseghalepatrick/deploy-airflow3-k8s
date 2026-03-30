from datetime import datetime

from airflow.sdk import dag
from airflow.providers.amazon.aws.transfers.local_to_s3 import LocalFilesystemToS3Operator
from airflow.providers.amazon.aws.operators.glue import GlueJobOperator

from produce_data import posts_asset, users_asset
from pathlib import Path

DAG_DIR = Path(__file__).resolve().parent

AWS_CONN_ID = "aws_conn"
AWS_REGION = "eu-west-1"

S3_BUCKET = "stackexchange-data-platform-joy"
LOCAL_GLUE_SCRIPT = str(DAG_DIR / "scripts" / "bronze_posts.py")
S3_GLUE_SCRIPT_KEY = "scripts/bronze_posts.py"

S3_GLUE_SCRIPT_PATH = f"s3://{S3_BUCKET}/{S3_GLUE_SCRIPT_KEY}"

GLUE_JOB_NAME = "bronze-posts-xml-to-iceberg"

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
        task_id="bronze_posts_glue_job",
        job_name=GLUE_JOB_NAME,
        script_location=S3_GLUE_SCRIPT_PATH,
        iam_role_name="GlueNotebookTutorialRole",
        region_name=AWS_REGION,
        aws_conn_id=AWS_CONN_ID,
        s3_bucket=S3_BUCKET,
        update_config=True,
        wait_for_completion=True,
        verbose=True,
        script_args={
            "--source_bucket": S3_BUCKET,
            "--source_key": "raw/posts/Posts.xml",
            "--catalog_database": "stackexchange_data_platform_db",
            "--catalog_table": "raw_posts",

            # Iceberg / Spark config from your notebook, translated to Glue job args
            "--datalake-formats": "iceberg",
            "--conf": (
                "spark.sql.extensions=org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions "
                "--conf spark.sql.catalog.glue_catalog=org.apache.iceberg.spark.SparkCatalog "
                "--conf spark.sql.catalog.glue_catalog.warehouse=s3://stackexchange-data-platform-joy/table/ "
                "--conf spark.sql.catalog.glue_catalog.catalog-impl=org.apache.iceberg.aws.glue.GlueCatalog "
                "--conf spark.sql.catalog.glue_catalog.io-impl=org.apache.iceberg.aws.s3.S3FileIO "
                "--conf spark.sql.sources.partitionOverwriteMode=dynamic "
                "--conf spark.sql.iceberg.handle-timestamp-without-timezone=true "
                "--conf spark.serializer=org.apache.spark.serializer.KryoSerializer "
                "--conf spark.sql.legacy.pathOptionBehavior.enabled=true"
            ),
        },
        create_job_kwargs={
            "GlueVersion": "5.0",
            "WorkerType": "G.1X",
            "NumberOfWorkers": 2,
            "ExecutionProperty": {
                "MaxConcurrentRuns": 1
            },
            "Command": {
                "Name": "glueetl",
                "ScriptLocation": S3_GLUE_SCRIPT_PATH,
                "PythonVersion": "3",
            },
            "DefaultArguments": {
                "--job-language": "python",
                "--enable-continuous-cloudwatch-log": "true",
                "--enable-metrics": "true",
            },
        },
        run_job_kwargs={
            "Timeout": 2880,
        },
    )

    upload_glue_script >> run_glue_job

upload_and_run_aws_glue_job()