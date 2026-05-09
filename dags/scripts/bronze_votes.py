import sys
import xml.etree.ElementTree as ET
from datetime import datetime

import boto3
from awsglue.context import GlueContext
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import SparkSession
from pyspark.sql.types import (
    LongType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)

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

spark = SparkSession.builder.appName(args["JOB_NAME"]).getOrCreate()
sc = SparkContext.getOrCreate()
glue_context = GlueContext(sc)

schema = StructType(
    [
        StructField("Id", LongType(), True),
        StructField("PostId", LongType(), True),
        StructField("VoteTypeId", LongType(), True),
        StructField("CreationDate", TimestampType(), True),
    ]
)


def to_long(value):
    try:
        return int(value) if value not in (None, "") else None
    except ValueError:
        return None


def to_timestamp(value):
    try:
        return datetime.fromisoformat(value) if value not in (None, "") else None
    except ValueError:
        return None


# Read XML from S3
s3 = boto3.client("s3")
obj = s3.get_object(Bucket=source_bucket, Key=source_key)
xml_content = obj["Body"].read()

# Parse XML
root = ET.fromstring(xml_content)
elements = root.findall("row")

if not elements:
    raise ValueError(f"No <row> elements found in s3://{source_bucket}/{source_key}")

rows = []
for elem in elements:
    attrib = elem.attrib
    rows.append(
        (
            to_long(attrib.get("Id")),
            to_long(attrib.get("PostId")),
            to_long(attrib.get("VoteTypeId")),
            to_timestamp(attrib.get("CreationDate")),
        )
    )

votes_df = spark.createDataFrame(rows, schema=schema)
votes_df.printSchema()
votes_df.show(5, truncate=True)

temp_view = "tmp_votes"
votes_df.createOrReplaceTempView(temp_view)

spark.sql(f"CREATE DATABASE IF NOT EXISTS glue_catalog.{catalog_database}")

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
