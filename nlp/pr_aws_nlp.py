import time
import boto3
from botocore.exceptions import ClientError
import json
import logging
from utils.opensearch import *


MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 10
client = OS_CLIENT
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
bedrock_client = boto3.client("bedrock-runtime", region_name="us-east-1")


def process_text(text):
    prompt = f"""**Instructions:**
    - **Act as a Natural Language Expert.**
    - Perform the following operations on the provided text:
      1. **Extract up to 5 named entities.** Return them as a list of strings.
      2. **Generate a concise 2-3 line summary.** Return it as a single string.
      3. **Identify up to 5 key topics or themes.** Return them as a list of strings.
    - **Return ONLY the results in valid JSON format** with the following exact structure:
      ```
      {{
        "entities": ["entity1", "entity2", ...],
        "topics": ["topic1", "topic2", ...],
        "summary": "Summary text here..."
      }}
      ```
    - **Ensure the output is nothing but the JSON object itself, starting with {{ and ending with }}.**

    **Input text:**
    {text}
    """
    native_request = {
        "message": prompt,
        "max_tokens": 512,
        "temperature": 0.5,
    }
    request = json.dumps(native_request)

    try:
        response = bedrock_client.invoke_model(modelId=BASE_MODEL_ID, body=request)
        response_body = json.loads(response["body"].read().decode("utf-8"))
        model_output_text = response_body.get("text")

        if not model_output_text:
            logging.error(
                f"LLM response structure unexpected or empty. Raw response: {response_body}"
            )
            return None

        # Clean potential markdown code fences strictly
        cleaned_response = model_output_text.strip()
        if cleaned_response.startswith("```"):
            cleaned_response = cleaned_response[7:]
        if cleaned_response.startswith("```"):
            cleaned_response = cleaned_response[3:]
        if cleaned_response.endswith("```"):
            cleaned_response = cleaned_response[:-3]
        cleaned_response = cleaned_response.strip()

        parsed_json = json.loads(cleaned_response)

        if not all(k in parsed_json for k in ["entities", "topics", "summary"]):
            logging.error(f"LLM JSON missing required keys. Parsed: {parsed_json}")
            return None

        entities = [
            {"text": entity, "label": "ENTITY"}
            for entity in parsed_json.get("entities", [])
        ]
        topics = [
            {"text": topic, "label": "TOPIC"} for topic in parsed_json.get("topics", [])
        ]
        output = {
            "entities": entities,
            "topics": topics,
            "summary": parsed_json.get("summary", ""),
        }
        return output

    except json.JSONDecodeError as json_e:
        logging.error(
            f"LLM response was not valid JSON after cleaning. Error: {json_e}. Response: '{model_output_text[:500]}...'"
        )
        return None
    except ClientError as boto_e:
        logging.error(f"Bedrock ClientError invoking '{BASE_MODEL_ID}': {boto_e}")
        return None
    except Exception as e:
        logging.error(
            f"Unexpected error processing text with '{BASE_MODEL_ID}': {e}",
            exc_info=True,
        )
        return None


def generate_embeddings(text):
    try:
        response = bedrock_client.invoke_model(
            modelId=EMBEDDING_MODEL_ID,
            contentType="application/json",
            accept="application/json",
            body=json.dumps({"inputText": text, "normalize": True, "dimensions": 256}),
        )
        embedding = json.loads(response["body"].read().decode("utf-8"))
        return embedding["embedding"]
    except Exception as e:
        print(f"Error generating embeddings with Titan: {e}")
        return None


def store_in_vector_index(document):
    try:
        response = client.index(index=VECTOR_INDEX_NAME, body=document)
        print(f"Document indexed successfully! ID: {response['_id']}")
        return response
    except Exception as e:
        print(f"Error indexing document: {e}")


def process_and_store_document(info):
    raw_text = info["content"]
    pr_url = info["pr_url"]
    pr_title = info["pr_title"]
    pr_date = info["pr_date"]
    document = process_text(raw_text)
    if document:
        document["pr_url"] = pr_url
        document["pr_title"] = pr_title
        document["pr_date"] = pr_date
        document["pr_content"] = info["content"]
        # Generate embeddings
        embedding = generate_embeddings(raw_text)

        if embedding:
            # Prepare document for indexing in OpenSearch vector index
            document["embedding"] = embedding

        # Store document in OpenSearch vector index
        store_in_vector_index(document)
        return document


def search_content_by_url(url, index_name=PR_META_RAW_IDX):
    query = {
        "bool": {"must": [{"term": {"pr_url.keyword": url}}]}  # Exact match on the URL
    }

    try:
        response = client.search(
            index=index_name,
            body={
                "query": query,
                "_source": [
                    "pr_url",
                    "pr_title",
                    "pr_date",
                    "content",
                ],  # Specify fields to return
                "size": 10000,  # Fetch up to 10,000 results
            },
        )
        return response["hits"]["hits"]
    except Exception as e:
        print(f"Error searching entries by URL: {e}")
        return []


def search_content_for_month(year: int, month: int, index_name: str = PR_META_RAW_IDX):
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
                "_source": ["pr_url", "pr_title", "pr_date", "content"],
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
        year, month, index_name=PR_META_RAW_IDX
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
    for target_year in range(2000, 2010):
        for target_month in range(1, 13):
            failed_urls = process_single_month_with_retry(target_year, target_month)

            if failed_urls:
                failure_filename = (
                    f"permanently_failed_urls_{target_year}_{target_month:02d}.txt"
                )
                try:
                    with open(failure_filename, "w") as f:
                        for url in failed_urls:
                            f.write(f"{url}\n")
                    logging.info(
                        f"List of permanently failed URLs saved to {failure_filename}"
                    )
                except IOError as e:
                    logging.error(
                        f"Failed to write failure file {failure_filename}: {e}"
                    )


if __name__ == "__main__":
    main()
