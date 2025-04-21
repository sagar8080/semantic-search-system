import json
import boto3
import os
from botocore.exceptions import ClientError


def get_secrets():
    secret_name = "credentials"
    region_name = "us-east-1"
    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name=region_name
    )
    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=secret_name
        )
    except ClientError as e:
        raise e

    secret = get_secret_value_response['SecretString']
    os.environ['credentials'] = secret
    return secret

def get_secret():
    try:
        secret = os.environ['credentials']
    except KeyError:
        secret = get_secrets()
    return json.loads(secret)