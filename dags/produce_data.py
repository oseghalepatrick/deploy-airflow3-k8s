import logging
import os

import py7zr
import requests
from airflow.providers.amazon.aws.hooks.s3 import S3Hook
from airflow.sdk import Asset, asset

posts_asset = Asset("s3://stackexchange-data-platform-joy/raw/posts/Posts.xml")
users_asset = Asset("s3://stackexchange-data-platform-joy/raw/users/Users.xml")
badges_asset = Asset("s3://stackexchange-data-platform-joy/raw/badges/Badges.xml")
comments_asset = Asset("s3://stackexchange-data-platform-joy/raw/comments/Comments.xml")
tags_asset = Asset("s3://stackexchange-data-platform-joy/raw/tags/Tags.xml")
votes_asset = Asset("s3://stackexchange-data-platform-joy/raw/votes/Votes.xml")


@asset.multi(schedule="@daily", outlets=[posts_asset, users_asset, badges_asset, comments_asset, tags_asset, votes_asset])
def produce_data_assets():
    # Define variables to download file and where to unzip
    key = "ai.meta.stackexchange.com"
    url = f"https://archive.org/download/stackexchange/{key}.7z"
    output_path = f"/tmp/{key}.7z"
    extract_path = f"/tmp/{key}"

    # Download the file
    logging.info(f"Downloading {url} to {output_path}")
    response = requests.get(url)
    response.raise_for_status()
    with open(output_path, "wb") as file:
        file.write(response.content)

    # Extract the zipped file
    logging.info(f"Extracting {output_path} to {extract_path}")
    with py7zr.SevenZipFile(output_path, mode="r") as archive:
        archive.extractall(path=extract_path)

    # Load the file to S3
    s3_hook = S3Hook(aws_conn_id="aws_conn")
    posts_file = os.path.join(extract_path, "Posts.xml")
    users_file = os.path.join(extract_path, "Users.xml")
    badges_file = os.path.join(extract_path, "Badges.xml")
    comments_file = os.path.join(extract_path, "Comments.xml")
    tags_file = os.path.join(extract_path, "Tags.xml")
    votes_file = os.path.join(extract_path, "Votes.xml")
    s3_hook.load_file(
        filename=posts_file,
        key="raw/posts/Posts.xml",
        bucket_name="stackexchange-data-platform-joy",
        replace=True,
    )
    s3_hook.load_file(
        filename=users_file,
        key="raw/users/Users.xml",
        bucket_name="stackexchange-data-platform-joy",
        replace=True,
    )
    s3_hook.load_file(
        filename=badges_file,
        key="raw/badges/Badges.xml",
        bucket_name="stackexchange-data-platform-joy",
        replace=True,
    )
    s3_hook.load_file(
        filename=comments_file,
        key="raw/comments/Comments.xml",
        bucket_name="stackexchange-data-platform-joy",
        replace=True,
    )
    s3_hook.load_file(
        filename=tags_file,
        key="raw/tags/Tags.xml",
        bucket_name="stackexchange-data-platform-joy",
        replace=True,
    )
    s3_hook.load_file(
        filename=votes_file,
        key="raw/votes/Votes.xml",
        bucket_name="stackexchange-data-platform-joy",
        replace=True,
    )
