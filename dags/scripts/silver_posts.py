import sys
from pyspark.context import SparkContext
from pyspark.sql import SparkSession, DataFrame
from pyspark.sql import functions as F
from pyspark.sql.types import StructType, StructField, IntegerType, StringType
from awsglue.context import GlueContext
from awsglue.utils import getResolvedOptions

# Get parameters passed into the job
args = getResolvedOptions(
    sys.argv,
    [
        "JOB_NAME",
        "catalog_database",
        "source_table",
        "target_table",
        "full_refresh",
    ],
)

catalog_database = args["catalog_database"]
source_table = args["source_table"]
target_table = args["target_table"]
full_refresh = args["full_refresh"].lower() == "true"

spark = SparkSession.builder.appName(args["JOB_NAME"]).getOrCreate()
sc = SparkContext.getOrCreate()
glue_context = GlueContext(sc)

# Define fully qualified names for the source and target tables
SOURCE_FQN = f"glue_catalog.{catalog_database}.{source_table}"
TARGET_FQN = f"glue_catalog.{catalog_database}.{target_table}"

# Functions to transform the data
def split_tag_into_array(df: DataFrame) -> DataFrame:
    return (
        df.withColumn(
            "TagsArray",
            F.filter(F.split(F.coalesce(F.col("Tags"), F.lit("")), r"\|"), lambda x: x != "")
        )
        .drop("Tags")
    )

def rename_columns(df: DataFrame) -> DataFrame:
    return df.withColumnRenamed("Id", "PostId")

def map_post_type(df: DataFrame) -> DataFrame:
    map_data = [
        (1, "Question"),
        (2, "Answer"),
        (3, "Orphaned tag wiki"),
        (4, "Tag wiki excerpt"),
        (5, "Tag wiki"),
        (6, "Moderator nomination"),
        (7, "Wiki placeholder"),
        (8, "Privilege wiki"),
        (9, "Article"),
        (10, "HelpArticle"),
        (12, "Collection"),
        (13, "ModeratorQuestionnaireResponse"),
        (14, "Announcement"),
        (15, "CollectiveDiscussion"),
        (17, "CollectiveCollection"),
    ]

    map_schema = StructType([
        StructField("PostTypeId", IntegerType(), False),
        StructField("PostType", StringType(), False),
    ])

    map_df = spark.createDataFrame(map_data, schema=map_schema)

    return (
        df.join(
            F.broadcast(map_df),
            df["PostTypeId"] == map_df["PostTypeId"],
            "left",
        )
        .drop(map_df["PostTypeId"])
    )

# Build the staging DataFrame
def build_stage_df() -> DataFrame:
    raw_posts_df = spark.table(SOURCE_FQN)

    stg_posts_df = (
        raw_posts_df
        .transform(split_tag_into_array)
        .transform(rename_columns)
        .transform(map_post_type)
    )

    return stg_posts_df

# Create target table if it doesn't exist
def create_target_table_if_needed(df: DataFrame) -> None:
    if not spark.catalog.tableExists(TARGET_FQN):
        (
            df.writeTo(TARGET_FQN)
            .tableProperty("format-version", "2")
            .create()
        )

# Full refresh table logic
def full_refresh_table(df: DataFrame) -> None:
    spark.sql(f"DROP TABLE IF EXISTS {TARGET_FQN}")
    (
        df.writeTo(TARGET_FQN)
        .tableProperty("format-version", "2")
        .create()
    )

# Incremental upsert logic
def incremental_upsert(df: DataFrame, unique_key: str, updated_at: str, full_refresh: bool) -> None:
    """
    Perform either a full refresh or an incremental upsert based on the `full_refresh` flag.
    If `full_refresh` is True, it will overwrite the entire table, otherwise it will do an incremental upsert.

    :param df: The DataFrame containing the data to write.
    :param unique_key: The unique key column for upsert (e.g., 'PostId').
    :param updated_at: The column used as the cursor for incremental updates (e.g., 'CreationDate').
    :param full_refresh: A flag to indicate whether to perform a full table overwrite (True) or incremental upsert (False).
    """
    
    # Create the target table if it doesn't exist
    create_target_table_if_needed(df)

    if full_refresh:
        # Full refresh: drop and recreate the table
        full_refresh_table(df)
        print("Full refresh completed, table overwritten.")
    else:
        # Incremental upsert: only update or insert new data
        last_max = (
            spark.table(TARGET_FQN)
            .agg(F.max(updated_at).alias("max_ts"))
            .collect()[0]["max_ts"]
        )

        # If no max value found, or no rows have been inserted before, treat it as a full refresh
        if last_max is None:
            incr_df = df
        else:
            incr_df = df.filter(F.col(updated_at) > F.lit(last_max))

        # If no incremental rows, no need to do the merge
        if incr_df.limit(1).count() == 0:
            print("No incremental rows to merge")
            return

        incr_df.createOrReplaceTempView("stg_posts_incr")

        # Perform the merge operation
        merge_sql = f"""
        MERGE INTO {TARGET_FQN} AS t
        USING stg_posts_incr AS s
        ON t.{unique_key} = s.{unique_key}
        WHEN MATCHED THEN UPDATE SET *
        WHEN NOT MATCHED THEN INSERT *
        """
        spark.sql(merge_sql)
        print("Incremental upsert completed.")

# Main logic to determine full refresh or incremental upsert
stg_posts_df = build_stage_df()

# Full refresh or incremental upsert based on the flag
incremental_upsert(
    df=stg_posts_df,
    unique_key="PostId",
    updated_at="CreationDate",
    full_refresh=full_refresh
)
