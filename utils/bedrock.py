import boto3
import json
import logging
from botocore.exceptions import ClientError
from utils.constants import *


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
bedrock_client = boto3.client("bedrock-runtime", region_name="us-east-1")


def engage_llm(prompt):
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
                f"Cohere response structure unexpected or empty. Raw response: {response_body}"
            )
            return None
        return model_output_text
    except Exception as e:
        print(e)
        return None
    
def generate_embeddings(text, model_id=EMBEDDING_MODEL_ID):
    try:
        response = bedrock_client.invoke_model(
            modelId=model_id,
            contentType="application/json",
            accept="application/json",
            body=json.dumps({"inputText": text, "normalize": True, "dimensions": 256}),
        )
        embedding = json.loads(response["body"].read().decode("utf-8"))
        return embedding[
            "embedding"
        ]
    except Exception as e:
        print(f"Error generating embeddings with Titan: {e}")
        return None