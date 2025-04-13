import json
import os
from opensearchpy import OpenSearch, RequestsHttpConnection, AWSV4SignerAuth
import boto3
from datetime import datetime
import time
from utils import *

PR_META_URL_IDX = "pr_meta_url_index"

client = get_os_client()


def add_processed_flag(data):
    for entry in data:
        entry["processed"] = False
    return data


def store_in_opensearch(data, index_name=PR_META_URL_IDX):
    try:
        response = client.search(
            index=index_name,
            body={
                "size": 1,
                "query": {"match_all": {}},
                "sort": [{"id": {"order": "desc"}}],
            },
        )
        if response["hits"]["hits"]:
            last_id = response["hits"]["hits"][0]["_source"]["id"]
            next_id = last_id + 1
        else:
            next_id = 1
    except Exception as e:
        print(f"Error retrieving last ID: {e}")
        next_id = 1
    time.sleep(3)
    for entry in data:
        try:
            entry["id"] = next_id
            client.index(index=index_name, id=next_id, body=entry)
            print(f"Stored entry with ID {next_id}")
            next_id += 1
        except Exception as e:
            print(f"Error storing entry {entry['pr_url']} in OpenSearch: {e}")


def process_json_file(file_path, index_name=PR_META_URL_IDX):
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return

    # Read the JSON file
    with open(file_path, "r") as file:
        data = json.load(file)

    # Add processed flag
    updated_data = add_processed_flag(data)

    # Store the data in OpenSearch
    store_in_opensearch(updated_data, index_name)


if __name__ == "__main__":
    file_path = "press_releases.json"
    index_body = {"settings": {"index": {"number_of_shards": 2}}}
    try:
        response = client.indices.create(PR_META_URL_IDX, body=index_body)
    except Exception as e:
        print(f"Error creating index: {e}")
    process_json_file(file_path)
