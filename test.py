import time
import boto3
from botocore.exceptions import ClientError
import json
import logging
from utils.opensearch import *


MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 10
client = OS_CLIENT
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")


def generate_text_embeddings(body):
    model_id = "cohere.embed-english-v3"
    accept = "*/*"
    content_type = "application/json"
    response = bedrock.invoke_model(
        body=body, modelId=model_id, accept=accept, contentType=content_type
    )
    response_body = json.loads(response.get("body").read())
    embeddings = response_body.get("embeddings")['int8'][0]
    print(embeddings, len(embeddings))
    return embeddings


def process_and_store_document(data):
    input_type = "search_document"
    embedding_types = ["int8"]
    text = "Title: " + data['pr_title'] + " " + "Summary:" + data['summary']
    body = json.dumps(
        {
            "texts": [data["summary"]],
            "input_type": input_type,
            "embedding_types": embedding_types,
            "truncate": "START"
        }
    )
    try:
        embeddings = generate_text_embeddings(body)
    except ClientError as err:
        message = err.response["Error"]["Message"]
        print("A client error occured: " + format(message))
        return False
    finally:
        return True


def search_content_for_month(
    year: int, month: int, index_name: str = PR_META_VECTOR_IDX
):
    if not 1 <= month <= 12:
        logging.error(f"Invalid month provided: {month}. Must be between 1 and 12.")
        return []

    start_date = f"{year}-{month:02d}-01"

    if month == 12:
        end_year = year + 1
        end_month = 1
    else:
        end_year = year
        end_month = month + 1
    end_date_exclusive = f"{end_year}-{end_month:02d}-01"

    logging.info(
        f"Searching index '{index_name}' for date range: >= {start_date} and < {end_date_exclusive}"
    )

    query = {"range": {"pr_date": {"gte": start_date, "lt": end_date_exclusive}}}

    try:
        response = client.search(
            index=index_name,
            body={
                "query": query,
                "_source": ["pr_url", "pr_title", "pr_date", "pr_content", "summary"],
                "size": 10000,
            },
        )
        hits = response.get("hits", {}).get("hits", [])
        logging.info(f"Found {len(hits)} documents for {year}-{month:02d}.")
        return hits
    except Exception as e:
        logging.error(
            f"Error searching index '{index_name}' for {year}-{month:02d}: {e}",
            exc_info=True,
        )
        return []


def process_single_month_with_retry(year: int, month: int):
    logging.info(f"=== Starting processing for {year}-{month:02d} ===")
    documents_to_process = search_content_for_month(
        year, month, index_name=PR_META_VECTOR_IDX
    )

    if not documents_to_process:
        logging.warning(
            f"No documents found or error occurred while searching for {year}-{month:02d}. Skipping processing."
        )
        return []

    permanently_failed_urls = []
    processed_count = 0
    failed_count = 0
    total_docs = len(documents_to_process)

    for idx, doc_hit in enumerate(documents_to_process):
        data = doc_hit.get("_source")
        pr_url = data.get("pr_url") if data else None

        if not data or not pr_url:
            logging.warning(
                f"Skipping hit {idx+1}/{total_docs} due to missing _source or pr_url. Doc ID: {doc_hit.get('_id')}"
            )
            continue

        logging.info(f"--- Processing document {idx+1}/{total_docs}: {pr_url} ---")
        success = False
        attempts = 0
        while attempts < MAX_RETRIES and not success:
            attempts += 1
            logging.info(f"Attempt {attempts}/{MAX_RETRIES} for URL: {pr_url}")
            try:
                # This function now contains all steps: LLM, Embed, Store
                success = process_and_store_document(data)
                if success:
                    logging.info(
                        f"Successfully processed and stored URL: {pr_url} (Doc {idx+1}/{total_docs})"
                    )
                else:
                    if attempts < MAX_RETRIES:
                        logging.warning(
                            f"Attempt {attempts} failed for {pr_url}. Retrying in {RETRY_DELAY_SECONDS}s..."
                        )
                        time.sleep(RETRY_DELAY_SECONDS)
            except Exception as e:
                logging.error(
                    f"Unexpected exception during attempt {attempts} for {pr_url}: {e}",
                    exc_info=True,
                )
                success = False
                if attempts < MAX_RETRIES:
                    logging.warning(
                        f"Attempt {attempts} failed unexpectedly for {pr_url}. Retrying in {RETRY_DELAY_SECONDS}s..."
                    )
                    time.sleep(RETRY_DELAY_SECONDS)
        if success:
            processed_count += 1
        else:
            logging.error(
                f"All {MAX_RETRIES} attempts failed for URL: {pr_url} (Doc {idx+1}/{total_docs})"
            )
            failed_count += 1
            permanently_failed_urls.append(pr_url)

    logging.info(f"=== Processing for {year}-{month:02d} Complete ===")
    logging.info(f"Total documents found: {total_docs}")
    logging.info(f"Successfully processed: {processed_count}")
    logging.info(f"Permanently failed after {MAX_RETRIES} retries: {failed_count}")
    if permanently_failed_urls:
        logging.warning("Permanently failed URLs:")
        for url in permanently_failed_urls:
            logging.warning(f"- {url}")

    return permanently_failed_urls


def main():
    for target_year in range(2025, 2026):
        for target_month in range(4, 5):
            failed_urls = process_single_month_with_retry(target_year, target_month)
            break

            # if failed_urls:
            #     failure_filename = (
            #         f"permanently_failed_urls_{target_year}_{target_month:02d}.txt"
            #     )
            #     try:
            #         with open(failure_filename, "w") as f:
            #             for url in failed_urls:
            #                 f.write(f"{url}\n")
            #         logging.info(
            #             f"List of permanently failed URLs saved to {failure_filename}"
            #         )
            #     except IOError as e:
            #         logging.error(
            #             f"Failed to write failure file {failure_filename}: {e}"
            #         )


if __name__ == "__main__":
    main()
