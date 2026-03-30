import sys
import boto3
import xml.etree.ElementTree as ET

from pyspark.context import SparkContext
from pyspark.sql import SparkSession, Row
from awsglue.context import GlueContext
from awsglue.utils import getResolvedOptions


args = getResolvedOptions(
    sys.argv,
    [
        "JOB_NAME",
        "source_bucket",
        "source_key",
        "catalog_database",
        "catalog_table",
    ],
)

source_bucket = args["source_bucket"]
source_key = args["source_key"]
catalog_database = args["catalog_database"]
catalog_table = args["catalog_table"]

# Spark / Glue contexts
spark = SparkSession.builder.appName(args["JOB_NAME"]).getOrCreate()
sc = SparkContext.getOrCreate()
glue_context = GlueContext(sc)

# Read XML from S3
s3 = boto3.client("s3")
obj = s3.get_object(Bucket=source_bucket, Key=source_key)
xml_content = obj["Body"].read()

# Parse XML
root = ET.fromstring(xml_content)
elements = root.findall("row")

if not elements:
    raise ValueError(f"No <row> elements found in s3://{source_bucket}/{source_key}")

# Collect every attribute that appears in any row
all_keys = set()
for elem in elements:
    all_keys.update(elem.attrib.keys())

# Build rows with None for missing attributes
rows = [
    Row(**{key: elem.attrib.get(key, None) for key in all_keys})
    for elem in elements
]

# Create Spark DataFrame
df = spark.createDataFrame(rows)
df.printSchema()

temp_view = "tmp_posts"
df.createOrReplaceTempView(temp_view)

# Create database if it does not exist
spark.sql(f"CREATE DATABASE IF NOT EXISTS glue_catalog.{catalog_database}")

# Recreate table each run for a clean raw landing
spark.sql(f"DROP TABLE IF EXISTS glue_catalog.{catalog_database}.{catalog_table}")

query = f"""
CREATE TABLE glue_catalog.{catalog_database}.{catalog_table}
USING iceberg
TBLPROPERTIES ("format-version"="2")
AS
SELECT * FROM {temp_view}
"""
spark.sql(query)

print(
    f"Created Iceberg table glue_catalog.{catalog_database}.{catalog_table} "
    f"from s3://{source_bucket}/{source_key}"
)