from opensearchpy import OpenSearch, RequestsHttpConnection, helpers, NotFoundError
from .get_secrets import get_secret
import logging

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
credentials = get_secret()
PR_META_URL_IDX = credentials.get("PR_META_URL_IDX")
VECTOR_INDEX_NAME = credentials.get('PR_META_VECTOR_IDX')
PR_META_RAW_IDX = credentials.get('PR_META_RAW_IDX')
BASE_MODEL_ID = "cohere.command-r-v1:0"
EMBEDDING_MODEL_ID = "amazon.titan-embed-text-v2:0"
PIPELINE_NAME = "hybrid_norm_pipeline"
REGION = "us-east-1"
PIPELINE_DEFINITION = {
    "description": "Pipeline for normalizing and combining lexical/semantic scores",
    "phase_results_processors": [
        {
            "normalization-processor": {
                "normalization": {"technique": "min_max"},
                "combination": {"technique": "arithmetic_mean"},
            }
        }
    ],
}

def get_os_client():
    host = credentials.get('OS_HOST')
    user = credentials.get("OS_UNAME")
    pwd = credentials.get("OS_PWD")
    auth = (user, pwd)
    os_client = OpenSearch(
        hosts=[{"host": host, "port": 443}],
        http_auth=auth,
        region=REGION,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
        pool_maxsize=20,
        timeout=60
    )
    return os_client

OS_CLIENT = get_os_client()


def create_search_pipeline(os_client, pipeline_name, pipeline_body):
    logging.info(f"Attempting to create/update search pipeline '{pipeline_name}'...")
    try:
        response = os_client.transport.perform_request(
            "PUT", f"/_search/pipeline/{pipeline_name}", body=pipeline_body
        )
        logging.info(
            f"Pipeline '{pipeline_name}' created/updated successfully: {response}"
        )
        return True
    except Exception as e:
        logging.error(
            f"Failed to create/update pipeline '{pipeline_name}': {e}", exc_info=True
        )
        return False


def set_default_search_pipeline(os_client, index_name, pipeline_name):
    logging.info(
        f"Attempting to set '{pipeline_name}' as default search pipeline for index '{index_name}'..."
    )
    try:
        response = os_client.indices.put_settings(
            index=index_name,
            body={"index.search.default_pipeline": pipeline_name},
        )
        if response.get("acknowledged"):
            logging.info(
                f"Successfully set default search pipeline for index '{index_name}'."
            )
            return True
        else:
            logging.warning(
                f"Setting default pipeline for '{index_name}' may not have been acknowledged: {response}"
            )
            return False
    except NotFoundError:
        logging.error(f"Index '{index_name}' not found. Cannot set default pipeline.")
        return False
    except Exception as e:
        logging.error(
            f"Failed to set default search pipeline for index '{index_name}': {e}",
            exc_info=True,
        )
        return False


# logging.info("--- Running One-Time Setup ---")
# pipeline_created = create_search_pipeline(OS_CLIENT, PIPELINE_NAME, PIPELINE_DEFINITION)
# default_set = set_default_search_pipeline(OS_CLIENT, VECTOR_INDEX_NAME, PIPELINE_NAME)
# logging.info("--- Completed Running Steup ---")
