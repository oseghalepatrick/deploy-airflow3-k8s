import sys
from pyspark.context import SparkContext
from pyspark.sql import SparkSession, DataFrame
from pyspark.sql import functions as F
from awsglue.context import GlueContext
from awsglue.utils import getResolvedOptions

# Fetching arguments from Glue job
args = getResolvedOptions(
    sys.argv,
    [
        "JOB_NAME",
        "catalog_database",
        "stg_posts_table",
        "marts_top_tags_table",
    ],
)

catalog_database = args["catalog_database"]
stg_posts_table = args["stg_posts_table"]
marts_top_tags_table = args["marts_top_tags_table"]

# Initialize Spark and Glue contexts
spark = SparkSession.builder.appName(args["JOB_NAME"]).getOrCreate()
sc = SparkContext.getOrCreate()
glue_context = GlueContext(sc)

# Define fully qualified names for source and target tables
SOURCE_FQN = f"glue_catalog.{catalog_database}.{stg_posts_table}"
TARGET_FQN = f"glue_catalog.{catalog_database}.{marts_top_tags_table}"

# Read the stg_posts table from Glue Catalog
stg_posts_df = spark.read.table(SOURCE_FQN)

def posts_top_tags(stg_posts_df: DataFrame) -> DataFrame:
    return (
        stg_posts_df
        .withColumn("tag_exploded", F.explode("TagsArray"))
        .groupBy("tag_exploded").agg(F.approx_count_distinct("PostId").alias("tags_count"))
        .orderBy(F.col("tags_count").desc())
    )

# Apply the transformation
marts_top_tags_df = posts_top_tags(stg_posts_df)

# Write the result to Glue as an Iceberg table
marts_top_tags_df.write.format("iceberg").mode("overwrite").saveAsTable(TARGET_FQN)

print(
    f"Created Iceberg table {TARGET_FQN} "
    f"from {SOURCE_FQN} "
)