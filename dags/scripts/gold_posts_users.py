import sys

from awsglue.context import GlueContext
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

# Fetching arguments from Airflow Glue job
args = getResolvedOptions(
    sys.argv,
    [
        "JOB_NAME",
        "catalog_database",
        "stg_posts_table",
        "raw_users_table",
        "marts_posts_users_table",
    ],
)

# Define the Glue context and Spark session
spark = SparkSession.builder.appName(args["JOB_NAME"]).getOrCreate()
sc = SparkContext.getOrCreate()
glue_context = GlueContext(sc)

# Define fully qualified table names from Glue catalog
catalog_database = args["catalog_database"]
stg_posts_table = args["stg_posts_table"]
raw_users_table = args["raw_users_table"]
marts_posts_users_table = args["marts_posts_users_table"]
stg_posts_table = f"glue_catalog.{catalog_database}.{stg_posts_table}"
raw_users_table = f"glue_catalog.{catalog_database}.{raw_users_table}"
marts_posts_users_table = f"glue_catalog.{catalog_database}.{marts_posts_users_table}"

# Read the tables from Glue
stg_posts_df = spark.read.table(stg_posts_table)
raw_users_df = spark.read.table(raw_users_table)


def posts_users_OBT(stg_posts_df: DataFrame, raw_users_df: DataFrame) -> DataFrame:
    return (
        stg_posts_df.alias("posts")
        .withColumnRenamed("CreationDate", "PostCreationDate")
        .join(
            other=raw_users_df.withColumnRenamed(
                "CreationDate", "UserCreationDate"
            ).alias("users"),
            on=F.col("posts.OwnerUserId") == F.col("users.Id"),
            how="left",
        )
    )


# Apply the function to merge posts and users
marts_posts_user_df = posts_users_OBT(stg_posts_df, raw_users_df)

# Write the result to Glue as an Iceberg table
marts_posts_user_df.write.format("iceberg").mode("overwrite").saveAsTable(
    marts_posts_users_table
)

print(
    f"Created Iceberg table {marts_posts_users_table} "
    f"from {stg_posts_table} "
    f"    and {raw_users_table}"
)
