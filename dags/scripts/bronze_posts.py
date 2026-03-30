import sys
import boto3
import xml.etree.ElementTree as ET
from datetime import datetime

from pyspark.context import SparkContext
from pyspark.sql import SparkSession, Row
from pyspark.sql.types import StructType, StructField, LongType, StringType, TimestampType
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

spark = SparkSession.builder.appName(args["JOB_NAME"]).getOrCreate()
sc = SparkContext.getOrCreate()
glue_context = GlueContext(sc)

schema = StructType([
    StructField("AcceptedAnswerId", LongType(), True),
    StructField("AnswerCount", LongType(), True),
    StructField("Body", StringType(), True),
    StructField("ClosedDate", TimestampType(), True),
    StructField("CommentCount", LongType(), True),
    StructField("CommunityOwnedDate", TimestampType(), True),
    StructField("ContentLicense", StringType(), True),
    StructField("CreationDate", TimestampType(), True),
    StructField("FavoriteCount", LongType(), True),
    StructField("Id", LongType(), True),
    StructField("LastActivityDate", TimestampType(), True),
    StructField("LastEditDate", TimestampType(), True),
    StructField("LastEditorDisplayName", StringType(), True),
    StructField("LastEditorUserId", LongType(), True),
    StructField("OwnerDisplayName", StringType(), True),
    StructField("OwnerUserId", LongType(), True),
    StructField("ParentId", LongType(), True),
    StructField("PostTypeId", LongType(), True),
    StructField("Score", LongType(), True),
    StructField("Tags", StringType(), True),
    StructField("Title", StringType(), True),
    StructField("ViewCount", LongType(), True)
])

def to_long(value):
    if value is None or value == "":
        return None
    return int(value)

def to_timestamp(value):
    if value is None or value == "":
        return None
    return datetime.fromisoformat(value)

s3 = boto3.client("s3")
obj = s3.get_object(Bucket=source_bucket, Key=source_key)
xml_content = obj["Body"].read()

root = ET.fromstring(xml_content)
elements = root.findall("row")

rows = []
for elem in elements:
    attrib = elem.attrib

    rows.append((
        to_long(attrib.get("AcceptedAnswerId")),
        to_long(attrib.get("AnswerCount")),
        attrib.get("Body"),
        to_timestamp(attrib.get("ClosedDate")),
        to_long(attrib.get("CommentCount")),
        to_timestamp(attrib.get("CommunityOwnedDate")),
        attrib.get("ContentLicense"),
        to_timestamp(attrib.get("CreationDate")),
        to_long(attrib.get("FavoriteCount")),
        to_long(attrib.get("Id")),
        to_timestamp(attrib.get("LastActivityDate")),
        to_timestamp(attrib.get("LastEditDate")),
        attrib.get("LastEditorDisplayName"),
        to_long(attrib.get("LastEditorUserId")),
        attrib.get("OwnerDisplayName"),
        to_long(attrib.get("OwnerUserId")),
        to_long(attrib.get("ParentId")),
        to_long(attrib.get("PostTypeId")),
        to_long(attrib.get("Score")),
        attrib.get("Tags"),
        attrib.get("Title"),
        to_long(attrib.get("ViewCount")),
    ))

df = spark.createDataFrame(rows, schema=schema)
df.printSchema()
df.show(5, truncate=False)

df.createOrReplaceTempView("tmp_posts")

spark.sql(f"CREATE DATABASE IF NOT EXISTS glue_catalog.{catalog_database}")
spark.sql(f"DROP TABLE IF EXISTS glue_catalog.{catalog_database}.{catalog_table}")

query = f"""
CREATE TABLE glue_catalog.{catalog_database}.{catalog_table}
USING iceberg
TBLPROPERTIES ("format-version"="2")
AS
SELECT * FROM tmp_posts
"""
spark.sql(query)
