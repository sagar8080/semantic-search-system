import os
import json
import boto3
from botocore.exceptions import ClientError
from opensearchpy import OpenSearch, RequestsHttpConnection, helpers

REGION = "us-east-1"

def get_secret():

    secret_name = "os_creds"
    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name=REGION
    )

    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=secret_name
        )
    except ClientError as e:
        raise e

    secret = get_secret_value_response['SecretString']
    return secret

secret = json.loads(get_secret())

def get_os_client():
    host = secret['OS_HOST']
    user = secret['OS_UNAME']
    pwd = secret['OS_PWD']
    auth = (user, pwd)
    os_client = OpenSearch(
        hosts=[{"host": host, "port": 443}],
        http_auth=auth,
        region=REGION,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
        pool_maxsize=20,
    )
    return os_client

PR_META_URL_IDX = secret['PR_META_URL_IDX']
VECTOR_INDEX_NAME = secret['VECTOR_INDEX_NAME']
PR_META_RAW_IDX = secret['PR_META_RAW_IDX']
BASE_MODEL_ID = "cohere.command-r-v1:0"
EMBEDDING_MODEL_ID = "amazon.titan-embed-text-v2:0"
PIPELINE_NAME = "hybrid_norm_pipeline"
OS_CLIENT = get_os_client()
    