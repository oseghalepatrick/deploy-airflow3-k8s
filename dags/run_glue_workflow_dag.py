from datetime import datetime
from pathlib import Path

from airflow.providers.amazon.aws.operators.glue import GlueJobOperator
from airflow.sdk import dag, task
from produce_data import posts_asset, users_asset

DAG_DIR = Path(__file__).resolve().parent

AWS_CONN_ID = "aws_conn"
AWS_REGION = "eu-west-1"
IAM_ROLE = "GlueNotebookTutorialRole"

S3_BUCKET = "stackexchange-data-platform-joy"

LOCAL_GLUE_SCRIPT = str(DAG_DIR / "scripts")
S3_GLUE_SCRIPT_KEY = "scripts"
S3_BRONZE_POSTS_GLUE_SCRIPT_KEY = "scripts/bronze_posts.py"
S3_BRONZE_USERS_GLUE_SCRIPT_KEY = "scripts/bronze_users.py"
S3_SILVER_POSTS_GLUE_SCRIPT_KEY = "scripts/silver_posts.py"

S3_BRONZE_POSTS_GLUE_SCRIPT_PATH = f"s3://{S3_BUCKET}/{S3_BRONZE_POSTS_GLUE_SCRIPT_KEY}"
S3_SILVER_POSTS_GLUE_SCRIPT_PATH = f"s3://{S3_BUCKET}/{S3_SILVER_POSTS_GLUE_SCRIPT_KEY}"
S3_BRONZE_USERS_GLUE_SCRIPT_PATH = f"s3://{S3_BUCKET}/{S3_BRONZE_USERS_GLUE_SCRIPT_KEY}"

GLUE_BRONZE_POSTS_JOB_NAME = "bronze-posts-xml-to-iceberg"
GLUE_SILVER_POSTS_JOB_NAME = "silver-posts-to-iceberg"
GLUE_BRONZE_USERS_JOB_NAME = "bronze-users-xml-to-iceberg"


@dag(
    dag_id="run_aws_glue_job",
    start_date=datetime(2026, 3, 30),
    schedule=(posts_asset & users_asset),
    catchup=False,
    tags=["aws", "glue", "s3"],
)
def upload_and_run_aws_glue_job():

    @task
    def upload_directory_to_s3(
        s3_bucket, local_directory, s3_key_prefix, aws_conn_id="aws_default"
    ):
        """
        Upload all files from the local directory to S3 in one task using AWS connection from Airflow.
        """

        import os

        import boto3
        from airflow.providers.amazon.aws.hooks.base_aws import AwsBaseHook

        # Use Airflow's AWS connection to get the credentials
        aws_hook = AwsBaseHook(aws_conn_id=aws_conn_id)
        credentials = aws_hook.get_credentials()

        # Create a boto3 client using the credentials from Airflow
        s3 = boto3.client(
            "s3",
            aws_access_key_id=credentials.access_key,
            aws_secret_access_key=credentials.secret_key,
            aws_session_token=credentials.session_token,
        )

        # Iterate over the local directory and upload files to S3
        for root, dirs, files in os.walk(local_directory):
            for file in files:
                local_file_path = os.path.join(root, file)
                s3_key = os.path.join(
                    s3_key_prefix, os.path.relpath(local_file_path, local_directory)
                )

                # Upload each file to S3
                s3.upload_file(local_file_path, s3_bucket, s3_key)
                print(f"Uploaded {local_file_path} to s3://{s3_bucket}/{s3_key}")

    # Usage in your DAG
    upload_task = upload_directory_to_s3(
        s3_bucket=S3_BUCKET,
        local_directory=LOCAL_GLUE_SCRIPT,
        s3_key_prefix=S3_GLUE_SCRIPT_KEY,
        aws_conn_id=AWS_CONN_ID
    )

    run_bronze_posts_glue_job = GlueJobOperator(
        task_id="run_bronze_posts_glue_job",
        job_name=GLUE_BRONZE_POSTS_JOB_NAME,
        script_location=S3_BRONZE_POSTS_GLUE_SCRIPT_PATH,
        iam_role_name=IAM_ROLE,
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
                f"--conf spark.sql.catalog.glue_catalog.warehouse=s3://{S3_BUCKET}/tables/ "
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
            "ExecutionProperty": {"MaxConcurrentRuns": 1},
            "Command": {
                "Name": "glueetl",
                "ScriptLocation": S3_BRONZE_POSTS_GLUE_SCRIPT_PATH,
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

    run_bronze_users_glue_job = GlueJobOperator(
        task_id="run_bronze_users_glue_job",
        job_name=GLUE_BRONZE_USERS_JOB_NAME,
        script_location=S3_BRONZE_USERS_GLUE_SCRIPT_PATH,
        iam_role_name=IAM_ROLE,
        region_name=AWS_REGION,
        aws_conn_id=AWS_CONN_ID,
        s3_bucket=S3_BUCKET,
        update_config=True,
        wait_for_completion=True,
        verbose=True,
        script_args={
            "--source_bucket": S3_BUCKET,
            "--source_key": "raw/users/Users.xml",
            "--catalog_database": "stackexchange_data_platform_db",
            "--catalog_table": "raw_users",
        },
        create_job_kwargs={
            "GlueVersion": "5.0",
            "WorkerType": "G.1X",
            "NumberOfWorkers": 2,
            "ExecutionProperty": {"MaxConcurrentRuns": 1},
            "Command": {
                "Name": "glueetl",
                "ScriptLocation": S3_BRONZE_USERS_GLUE_SCRIPT_PATH,
                "PythonVersion": "3",
            },
            "DefaultArguments": {
                "--job-language": "python",
                "--datalake-formats": "iceberg",
                "--enable-continuous-cloudwatch-log": "true",
                "--enable-metrics": "true",
                "--conf": (
                    "spark.sql.extensions=org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions "
                    "--conf spark.sql.catalog.glue_catalog=org.apache.iceberg.spark.SparkCatalog "
                    f"--conf spark.sql.catalog.glue_catalog.warehouse=s3://{S3_BUCKET}/tables/ "
                    "--conf spark.sql.catalog.glue_catalog.catalog-impl=org.apache.iceberg.aws.glue.GlueCatalog "
                    "--conf spark.sql.catalog.glue_catalog.io-impl=org.apache.iceberg.aws.s3.S3FileIO "
                    "--conf spark.sql.sources.partitionOverwriteMode=dynamic "
                    "--conf spark.sql.iceberg.handle-timestamp-without-timezone=true "
                    "--conf spark.serializer=org.apache.spark.serializer.KryoSerializer "
                    "--conf spark.sql.legacy.pathOptionBehavior.enabled=true"
                ),
            },
        },
        run_job_kwargs={
            "Timeout": 2880,
        },
    )

    # Glue job task to process data
    run_silver_posts_glue_job = GlueJobOperator(
        task_id="run_silver_posts_glue_job",
        job_name=GLUE_SILVER_POSTS_JOB_NAME,
        script_location=S3_SILVER_POSTS_GLUE_SCRIPT_PATH,
        iam_role_name=IAM_ROLE,
        region_name=AWS_REGION,
        aws_conn_id=AWS_CONN_ID,
        s3_bucket=S3_BUCKET,
        update_config=True,
        wait_for_completion=True,
        verbose=True,
        script_args={
            "--catalog_database": "stackexchange_data_platform_db",
            "--source_table": "raw_posts",
            "--target_table": "silver_posts",
            "--full_refresh": "true",
        },
        create_job_kwargs={
            "GlueVersion": "5.0",
            "WorkerType": "G.1X",
            "NumberOfWorkers": 2,
            "ExecutionProperty": {"MaxConcurrentRuns": 1},
            "Command": {
                "Name": "glueetl",
                "ScriptLocation": S3_SILVER_POSTS_GLUE_SCRIPT_PATH,
                "PythonVersion": "3",
            },
            "DefaultArguments": {
                "--job-language": "python",
                "--datalake-formats": "iceberg",
                "--enable-continuous-cloudwatch-log": "true",
                "--enable-metrics": "true",
                "--conf": (
                    "spark.sql.extensions=org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions "
                    "--conf spark.sql.catalog.glue_iceberg=org.apache.iceberg.spark.SparkCatalog "
                    "--conf spark.sql.catalog.glue_iceberg.warehouse=s3://stackexchange-data-platform-joy/tables/ "
                    "--conf spark.sql.catalog.glue_iceberg.type=glue "
                    "--conf spark.sql.sources.partitionOverwriteMode=dynamic "
                    "--conf spark.sql.iceberg.handle-timestamp-without-timezone=true "
                    "--conf spark.serializer=org.apache.spark.serializer.KryoSerializer "
                    "--conf spark.sql.legacy.pathOptionBehavior.enabled=true"
                ),
            },
        },
        run_job_kwargs={
            "Timeout": 2880,
        },
    )

    upload_task >> run_bronze_posts_glue_job >> run_silver_posts_glue_job
    upload_task >> run_bronze_users_glue_job


upload_and_run_aws_glue_job()
