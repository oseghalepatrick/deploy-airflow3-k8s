from datetime import datetime
from pathlib import Path

from airflow.sdk.bases.operator import chain
from airflow.providers.amazon.aws.operators.glue import GlueJobOperator
from airflow.sdk import dag, task
from produce_data import (
    badges_asset,
    comments_asset,
    posts_asset,
    tags_asset,
    users_asset,
    votes_asset,
)

DAG_DIR = Path(__file__).resolve().parent

AWS_CONN_ID = "aws_conn"
AWS_REGION = "eu-west-1"
IAM_ROLE = "GlueNotebookTutorialRole"

S3_BUCKET = "stackexchange-data-platform-joy"
GLUE_DB = "stackexchange_data_platform_db"

LOCAL_GLUE_SCRIPT = str(DAG_DIR / "scripts")
S3_GLUE_SCRIPT_KEY = "scripts"
S3_BRONZE_POSTS_GLUE_SCRIPT_KEY = "scripts/bronze_posts.py"
S3_BRONZE_USERS_GLUE_SCRIPT_KEY = "scripts/bronze_users.py"
S3_BRONZE_BADGES_GLUE_SCRIPT_KEY = "scripts/bronze_badges.py"
S3_BRONZE_COMMENTS_GLUE_SCRIPT_KEY = "scripts/bronze_comments.py"
S3_BRONZE_TAGS_GLUE_SCRIPT_KEY = "scripts/bronze_tags.py"
S3_BRONZE_VOTES_GLUE_SCRIPT_KEY = "scripts/bronze_votes.py"
S3_SILVER_POSTS_GLUE_SCRIPT_KEY = "scripts/silver_posts.py"
S3_GOLD_POSTS_USERS_GLUE_SCRIPT_KEY = "scripts/gold_posts_users.py"
S3_GOLD_POPULAR_TAGS_GLUE_SCRIPT_KEY = "scripts/gold_most_popular_tags.py"

S3_BRONZE_POSTS_GLUE_SCRIPT_PATH = f"s3://{S3_BUCKET}/{S3_BRONZE_POSTS_GLUE_SCRIPT_KEY}"
S3_SILVER_POSTS_GLUE_SCRIPT_PATH = f"s3://{S3_BUCKET}/{S3_SILVER_POSTS_GLUE_SCRIPT_KEY}"
S3_BRONZE_USERS_GLUE_SCRIPT_PATH = f"s3://{S3_BUCKET}/{S3_BRONZE_USERS_GLUE_SCRIPT_KEY}"

S3_BRONZE_BADGES_GLUE_SCRIPT_PATH = f"s3://{S3_BUCKET}/{S3_BRONZE_BADGES_GLUE_SCRIPT_KEY}"
S3_BRONZE_COMMENTS_GLUE_SCRIPT_PATH = f"s3://{S3_BUCKET}/{S3_BRONZE_COMMENTS_GLUE_SCRIPT_KEY}"
S3_BRONZE_TAGS_GLUE_SCRIPT_PATH = f"s3://{S3_BUCKET}/{S3_BRONZE_TAGS_GLUE_SCRIPT_KEY}"
S3_BRONZE_VOTES_GLUE_SCRIPT_PATH = f"s3://{S3_BUCKET}/{S3_BRONZE_VOTES_GLUE_SCRIPT_KEY}"

S3_GOLD_POSTS_USERS_GLUE_SCRIPT_PATH = (
    f"s3://{S3_BUCKET}/{S3_GOLD_POSTS_USERS_GLUE_SCRIPT_KEY}"
)
S3_GOLD_POPULAR_TAGS_GLUE_SCRIPT_PATH = (
    f"s3://{S3_BUCKET}/{S3_GOLD_POPULAR_TAGS_GLUE_SCRIPT_KEY}"
)

GLUE_BRONZE_POSTS_JOB_NAME = "bronze-posts-xml-to-iceberg"
GLUE_BRONZE_USERS_JOB_NAME = "bronze-users-xml-to-iceberg"

GLUE_BRONZE_BADGES_JOB_NAME = "bronze-badges-xml-to-iceberg"
GLUE_BRONZE_COMMENTS_JOB_NAME = "bronze-comments-xml-to-iceberg"
GLUE_BRONZE_TAGS_JOB_NAME = "bronze-tags-xml-to-iceberg"
GLUE_BRONZE_VOTES_JOB_NAME = "bronze-votes-xml-to-iceberg"

GLUE_SILVER_POSTS_JOB_NAME = "silver-posts-to-iceberg"
GLUE_GOLD_POSTS_USERS_JOB_NAME = "gold-posts-users-to-iceberg"
GLUE_GOLD_POPULAR_TAGS_JOB_NAME = "gold-popular-tags-to-iceberg"


def get_create_job_kwargs(script_path: str, s3_bucket) -> dict:
    # Reusable create_job_kwargs (with Iceberg configurations)
    create_job_kwargs = {
        "GlueVersion": "5.0",
        "WorkerType": "G.1X",
        "NumberOfWorkers": 2,
        "ExecutionProperty": {"MaxConcurrentRuns": 1},
        "Command": {
            "Name": "glueetl",
            "ScriptLocation": script_path,
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
                f"--conf spark.sql.catalog.glue_catalog.warehouse=s3://{s3_bucket}/tables/ "
                "--conf spark.sql.catalog.glue_catalog.type=glue "
                "--conf spark.sql.sources.partitionOverwriteMode=dynamic "
                "--conf spark.sql.iceberg.handle-timestamp-without-timezone=true "
                "--conf spark.serializer=org.apache.spark.serializer.KryoSerializer "
                "--conf spark.sql.legacy.pathOptionBehavior.enabled=true"
            ),
        },
    }

    return create_job_kwargs


@dag(
    dag_id="run_aws_glue_job",
    start_date=datetime(2026, 3, 30),
    schedule=(posts_asset & users_asset & badges_asset & comments_asset & tags_asset & votes_asset),
    max_active_runs=1,
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
        aws_conn_id=AWS_CONN_ID,
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
            "--catalog_database": GLUE_DB,
            "--catalog_table": "raw_posts",
        },
        create_job_kwargs=get_create_job_kwargs(
            S3_BRONZE_POSTS_GLUE_SCRIPT_PATH, S3_BUCKET
        ),
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
            "--catalog_database": GLUE_DB,
            "--catalog_table": "raw_users",
        },
        create_job_kwargs=get_create_job_kwargs(
            S3_BRONZE_USERS_GLUE_SCRIPT_PATH, S3_BUCKET
        ),
        run_job_kwargs={
            "Timeout": 2880,
        },
    )

    ###############################


    run_bronze_badges_glue_job = GlueJobOperator(
        task_id="run_bronze_badges_glue_job",
        job_name=GLUE_BRONZE_BADGES_JOB_NAME,
        script_location=S3_BRONZE_BADGES_GLUE_SCRIPT_PATH,
        iam_role_name=IAM_ROLE,
        region_name=AWS_REGION,
        aws_conn_id=AWS_CONN_ID,
        s3_bucket=S3_BUCKET,
        update_config=True,
        wait_for_completion=True,
        verbose=True,
        script_args={
            "--source_bucket": S3_BUCKET,
            "--source_key": "raw/badges/Badges.xml",
            "--catalog_database": GLUE_DB,
            "--catalog_table": "raw_badges",
        },
        create_job_kwargs=get_create_job_kwargs(
            S3_BRONZE_BADGES_GLUE_SCRIPT_PATH, S3_BUCKET
        ),
        run_job_kwargs={
            "Timeout": 2880,
        },
    )

    run_bronze_comments_glue_job = GlueJobOperator(
        task_id="run_bronze_comments_glue_job",
        job_name=GLUE_BRONZE_COMMENTS_JOB_NAME,
        script_location=S3_BRONZE_COMMENTS_GLUE_SCRIPT_PATH,
        iam_role_name=IAM_ROLE,
        region_name=AWS_REGION,
        aws_conn_id=AWS_CONN_ID,
        s3_bucket=S3_BUCKET,
        update_config=True,
        wait_for_completion=True,
        verbose=True,
        script_args={
            "--source_bucket": S3_BUCKET,
            "--source_key": "raw/comments/Comments.xml",
            "--catalog_database": GLUE_DB,
            "--catalog_table": "raw_comments",
        },
        create_job_kwargs=get_create_job_kwargs(
            S3_BRONZE_COMMENTS_GLUE_SCRIPT_PATH, S3_BUCKET
        ),
        run_job_kwargs={
            "Timeout": 2880,
        },
    )

    run_bronze_tags_glue_job = GlueJobOperator(
        task_id="run_bronze_tags_glue_job",
        job_name=GLUE_BRONZE_TAGS_JOB_NAME,
        script_location=S3_BRONZE_TAGS_GLUE_SCRIPT_PATH,
        iam_role_name=IAM_ROLE,
        region_name=AWS_REGION,
        aws_conn_id=AWS_CONN_ID,
        s3_bucket=S3_BUCKET,
        update_config=True,
        wait_for_completion=True,
        verbose=True,
        script_args={
            "--source_bucket": S3_BUCKET,
            "--source_key": "raw/tags/Tags.xml",
            "--catalog_database": GLUE_DB,
            "--catalog_table": "raw_tags",
        },
        create_job_kwargs=get_create_job_kwargs(
            S3_BRONZE_TAGS_GLUE_SCRIPT_PATH, S3_BUCKET
        ),
        run_job_kwargs={
            "Timeout": 2880,
        },
    )

    run_bronze_votes_glue_job = GlueJobOperator(
        task_id="run_bronze_votes_glue_job",
        job_name=GLUE_BRONZE_VOTES_JOB_NAME,
        script_location=S3_BRONZE_VOTES_GLUE_SCRIPT_PATH,
        iam_role_name=IAM_ROLE,
        region_name=AWS_REGION,
        aws_conn_id=AWS_CONN_ID,
        s3_bucket=S3_BUCKET,
        update_config=True,
        wait_for_completion=True,
        verbose=True,
        script_args={
            "--source_bucket": S3_BUCKET,
            "--source_key": "raw/votes/Votes.xml",
            "--catalog_database": GLUE_DB,
            "--catalog_table": "raw_votes",
        },
        create_job_kwargs=get_create_job_kwargs(
            S3_BRONZE_VOTES_GLUE_SCRIPT_PATH, S3_BUCKET
        ),
        run_job_kwargs={
            "Timeout": 2880,
        },
    )

    ###############################

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
            "--catalog_database": GLUE_DB,
            "--source_table": "raw_posts",
            "--target_table": "silver_posts",
            "--full_refresh": "true",
        },
        create_job_kwargs=get_create_job_kwargs(
            S3_SILVER_POSTS_GLUE_SCRIPT_PATH, S3_BUCKET
        ),
        run_job_kwargs={
            "Timeout": 2880,
        },
    )

    run_posts_users_glue_job = GlueJobOperator(
        task_id="run_posts_users_glue_job",
        job_name=GLUE_GOLD_POSTS_USERS_JOB_NAME,
        script_location=S3_GOLD_POSTS_USERS_GLUE_SCRIPT_PATH,
        iam_role_name=IAM_ROLE,
        region_name=AWS_REGION,
        aws_conn_id=AWS_CONN_ID,
        s3_bucket=S3_BUCKET,
        update_config=True,
        wait_for_completion=True,
        verbose=True,
        script_args={
            "--catalog_database": GLUE_DB,
            "--stg_posts_table": "silver_posts",
            "--raw_users_table": "raw_users",
            "--marts_posts_users_table": "marts_posts_users",
        },
        create_job_kwargs=get_create_job_kwargs(
            S3_GOLD_POSTS_USERS_GLUE_SCRIPT_PATH, S3_BUCKET
        ),
        run_job_kwargs={
            "Timeout": 2880,
        },
    )

    run_top_tags_glue_job = GlueJobOperator(
        task_id="run_top_tags_glue_job",
        job_name=GLUE_GOLD_POPULAR_TAGS_JOB_NAME,
        script_location=S3_GOLD_POPULAR_TAGS_GLUE_SCRIPT_PATH,
        iam_role_name=IAM_ROLE,
        region_name=AWS_REGION,
        aws_conn_id=AWS_CONN_ID,
        s3_bucket=S3_BUCKET,
        update_config=True,
        wait_for_completion=True,
        verbose=True,
        script_args={
            "--catalog_database": GLUE_DB,
            "--stg_posts_table": "silver_posts",
            "--marts_top_tags_table": "marts_top_tags",
        },
        create_job_kwargs=get_create_job_kwargs(
            S3_GOLD_POPULAR_TAGS_GLUE_SCRIPT_PATH, S3_BUCKET
        ),
        run_job_kwargs={
            "Timeout": 2880,
        },
    )

    chain(
        upload_task,
        [
            run_bronze_posts_glue_job,
            run_bronze_users_glue_job,
            run_bronze_badges_glue_job,
            run_bronze_comments_glue_job,
            run_bronze_tags_glue_job,
            run_bronze_votes_glue_job
        ],
        run_silver_posts_glue_job,
        [
            run_posts_users_glue_job,
            run_top_tags_glue_job
        ]
    )


upload_and_run_aws_glue_job()
