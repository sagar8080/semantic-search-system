from opensearchpy import OpenSearch, RequestsHttpConnection, AWSV4SignerAuth, helpers
import boto3
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import re
import time
from utils import *

region = "us-east-1"
client = OS_CLIENT


def check_index_exists(index_name):
    return client.indices.exists(index=index_name)


def create_index(index_name):
    index_body = {"settings": {"index": {"number_of_shards": 2}}}
    try:
        response = client.indices.create(index_name, body=index_body)
    except Exception as e:
        print(f"Error creating index: {e}")


def clean_text(text):
    text = re.sub(r"[^a-zA-Z0-9\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def fetch_press_release_info(url):
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")

        # Extract title
        title = soup.find("h1").text.strip() if soup.find("h1") else "No Title Found"
        body = (
            soup.find("div", class_="page__content evo-page-content")
            .contents[0]
            .find("div", class_="evo-press-release__body")
        )
        content = body.text.strip() if body else "No content Found"
        return clean_text(content)
    except requests.exceptions.RequestException as e:
        print(f"Request error for {url}: {e}")
        return None
    except Exception as e:
        print(f"An error occurred for {url}: {e}")
        return None


def search_unprocessed_entries(index_name=PR_META_URL_IDX):
    try:
        response = client.search(
            index=index_name, body={"query": {"term": {"processed": False}}}, size=10000
        )
        return response["hits"]["hits"]
    except Exception as e:
        print(f"Error searching unprocessed entries: {e}")
        return []


def search_unprocessed_entries_by_date(
    year=None, month=None, index_name=PR_META_URL_IDX
):
    query = {"bool": {"must": [{"term": {"processed": False}}]}}

    if year:
        query["bool"]["filter"] = [
            {"range": {"pr_date": {"gte": f"{year}-01-01", "lt": f"{year + 1}-01-01"}}}
        ]

    if month:
        query["bool"]["filter"].append(
            {
                "range": {
                    "pr_date": {
                        "gte": f"{year}-{month:02d}-01",
                        "lt": f"{year}-{month+1:02d}-01",
                    }
                }
            }
        )
    try:
        response = client.search(index=index_name, body={"query": query}, size=10000)
        return response["hits"]["hits"]
    except Exception as e:
        print(f"Error searching unprocessed entries by date: {e}")
        return []


def store_in_opensearch(identifier, data, index_name):
    try:
        # Add the auto-incrementing ID
        data["id"] = identifier
        client.index(index=index_name, id=identifier, body=data)
        print(f"Stored entry with ID {identifier}")
    except Exception as e:
        print(
            f"Error storing entry {data['pr_url']} with identiifier {identifier} in OpenSearch: {e}"
        )


def update_processed_flag(identifier, index_name=PR_META_URL_IDX):
    try:
        client.update(
            index=index_name,
            id=identifier,
            body={"doc": {"processed": True}},
        )
        print(f"Updated processed flag for {identifier}")
    except Exception as e:
        print(f"Error updating processed flag for {identifier}: {e}")


def bulk_update_processed_flags(ids, index_name=PR_META_URL_IDX):
    """
    Update the processed flag for multiple documents in bulk
    """
    bulk_actions = []
    for doc_id in ids:
        action = {
            "_op_type": "update",
            "_index": index_name,
            "_id": doc_id,
            "doc": {"processed": True},
        }
        bulk_actions.append(action)

    try:
        if bulk_actions:
            success, failed = helpers.bulk(client, bulk_actions, stats_only=True)
            failed = failed if isinstance(failed, int) else len(failed)
            print(f"Bulk update processed flags: {success} succeeded, {failed} failed")
    except Exception as e:
        print(f"Error in bulk update of processed flags: {e}")


def process_skipped_entries():
    unprocessed_entries = search_unprocessed_entries()
    print(f"Unprocessed entries: {len(unprocessed_entries)}")

    bulk_raw_actions = []
    processed_ids = []

    for entry in unprocessed_entries:
        pr_id = entry["_id"]
        pr_url = entry["_source"]["pr_url"]
        pr_date = entry["_source"]["pr_date"]
        try:
            pr_title = entry["_source"]["pr_title"]
        except KeyError:
            pr_title = entry["_source"]["pr_pr_title"]
        content = fetch_press_release_info(pr_url)
        if not content:
            print(f"No content found for {pr_url}, skipping")
            continue

        # Prepare the data to store in PR_META_RAW_IDX
        raw_data = {
            "pr_url": pr_url,
            "pr_date": pr_date,
            "pr_title": pr_title,
            "content": content,
        }

        # Add to bulk actions
        action = {
            "_op_type": "index",
            "_index": PR_META_RAW_IDX,
            "_id": pr_id,
            "_source": raw_data,
        }
        bulk_raw_actions.append(action)
        processed_ids.append(pr_id)

    # Perform bulk insert for raw data
    if bulk_raw_actions:
        try:
            success, failed = helpers.bulk(client, bulk_raw_actions, stats_only=True)
            failed = failed if isinstance(failed, int) else len(failed)
            print(
                f"Bulk insert to {PR_META_RAW_IDX}: {success} succeeded, {failed} failed"
            )
            if success > 0:
                bulk_update_processed_flags(processed_ids)
        except Exception as e:
            print(f"Error in bulk insert to {PR_META_RAW_IDX}: {e}")
    print("************************************")
    print(f"Completed processing")
    print("************************************")


def process_entries():
    ym_tuple = [(y, m) for y in range(2000, 2025) for m in range(1, 13)]

    if not check_index_exists(PR_META_RAW_IDX):
        create_index(PR_META_RAW_IDX)

    for year, month in ym_tuple:
        print(f"Processing year: {year}, month: {month}")
        unprocessed_entries_by_date = search_unprocessed_entries_by_date(
            year=year, month=month
        )
        print(
            f"Unprocessed entries for {year}-{month}: {len(unprocessed_entries_by_date)}"
        )
        bulk_raw_actions = []
        processed_ids = []

        for entry in unprocessed_entries_by_date:
            pr_id = entry["_id"]
            pr_url = entry["_source"]["pr_url"]
            pr_date = entry["_source"]["pr_date"]
            try:
                pr_title = entry["_source"]["pr_title"]
            except KeyError:
                pr_title = entry["_source"]["pr_pr_title"]
            content = fetch_press_release_info(pr_url)
            if not content:
                print(f"No content found for {pr_url}, skipping")
                continue

            # Prepare the data to store in PR_META_RAW_IDX
            raw_data = {
                "pr_url": pr_url,
                "pr_date": pr_date,
                "pr_title": pr_title,
                "content": content,
            }

            # Add to bulk actions
            action = {
                "_op_type": "index",
                "_index": PR_META_RAW_IDX,
                "_id": pr_id,
                "_source": raw_data,
            }
            bulk_raw_actions.append(action)
            processed_ids.append(pr_id)

        # Perform bulk insert for raw data
        if bulk_raw_actions:
            try:
                success, failed = helpers.bulk(
                    client, bulk_raw_actions, stats_only=True
                )
                failed = failed if isinstance(failed, int) else len(failed)
                print(
                    f"Bulk insert to {PR_META_RAW_IDX}: {success} succeeded, {failed} failed"
                )
                if success > 0:
                    bulk_update_processed_flags(processed_ids)
            except Exception as e:
                print(f"Error in bulk insert to {PR_META_RAW_IDX}: {e}")
        print("************************************")
        print(f"Completed processing: {year}-{month}")
        print("************************************")


process_entries()
process_skipped_entries()
print("Processing complete")
client.close()
