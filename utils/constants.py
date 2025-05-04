from .get_secrets import get_secret

BEDROCK_RERANKER_MODEL_ARN = "arn:aws:bedrock:us-west-2::foundation-model/amazon.rerank-v1:0"
CROSS_ENCODER_MODEL_NAME = 'BAAI/bge-reranker-base'
BASE_MODEL_ID = "cohere.command-r-v1:0"
EMBEDDING_MODEL_ID = "amazon.titan-embed-text-v2:0"
PIPELINE_NAME = "hybrid_norm_pipeline"
REGION = "us-east-1"
credentials = get_secret()
PR_META_URL_IDX = credentials.get("PR_META_URL_IDX")
PR_META_VECTOR_IDX = credentials.get('PR_META_VECTOR_IDX')
PR_META_RAW_IDX = credentials.get('PR_META_RAW_IDX')
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