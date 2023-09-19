from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Callable, Iterable
import boto3
import time


dynamodb = boto3.resource("dynamodb", endpoint_url="http://localhost:8000")


def reset_db(config, force=False):
    table_def = config["table"]
    pk, sk = table_def["key"]
    gsi = table_def.get("indexes", [])

    key_schema = [
        {"AttributeName": pk["pk"], "KeyType": "HASH"},
    ]

    attr_defs = [
        {"AttributeName": pk["pk"], "AttributeType": pk["type"]},
    ]

    if sk and sk.get("sk"):
        key_schema.append({"AttributeName": sk["sk"], "KeyType": "RANGE"})
        attr_defs.append({"AttributeName": sk["sk"], "AttributeType": sk["type"]})

    indexes = create_indexes_params(gsi, attr_defs)

    if force:
        try_delete_db(table_def["name"])

    print(f"Creating table {table_def['name']}")

    # Create the DynamoDB table if it doesn't exist
    create_params = dict(
        TableName=table_def["name"],
        KeySchema=key_schema,
        AttributeDefinitions=attr_defs,
        BillingMode="PAY_PER_REQUEST",
        GlobalSecondaryIndexes=indexes,
        StreamSpecification={
            "StreamEnabled": True,
            "StreamViewType": "NEW_AND_OLD_IMAGES",
        }
    )

    if table_def.get("stream"):
        view_type = table_def["stream"].get("view_type")
        create_params["StreamSpecification"] = {
            "StreamEnabled": True,
            "StreamViewType": view_type  or  "NEW_AND_OLD_IMAGES",
            "BatchSize": table_def["stream"].get("batch_size") or 100,
        }
    try:
        dynamodb.create_table(**create_params)
        print(f"{table_def['name']} created!")
    except dynamodb.meta.client.exceptions.ResourceInUseException:
        print(f"{table_def['name']} already exists!")


def try_delete_db(table_name):
    print(f"Deleting table {table_name}")
    try:
        table = dynamodb.Table(table_name)
        table.delete()
        print(f"{table_name} deleted!")
    except dynamodb.meta.client.exceptions.ResourceNotFoundException:
        print(f"{table_name} not found!")


def create_indexes_params(gsi, attr_defs):
    indexs = []
    for index in gsi:
        pk, sk = index["key"]
        idx_key_schema = [
            {"AttributeName": pk["pk"], "KeyType": "HASH"},
        ]

        if sk and sk.get("sk"):
            idx_key_schema.append({"AttributeName": sk["sk"], "KeyType": "RANGE"})
            attr_defs.append({"AttributeName": sk["sk"], "AttributeType": sk["type"]})

        indexs.append(
            {
                "IndexName": index["name"],
                "KeySchema": idx_key_schema,
                "Projection": {"ProjectionType": "ALL"},
            }
        )

        attr_defs.append({"AttributeName": pk["pk"], "AttributeType": pk["type"]})

    return indexs


def load_data(table_name, data):
    table = dynamodb.Table(table_name)
    with table.batch_writer() as batch:
        for item in data:
            batch.put_item(Item=_serialize(item))


def _serialize(item: dict):
    for k, v in item.items():
        if isinstance(v, dict):
            item[k] = _serialize(v)
        elif isinstance(v, list):
            item[k] = [_serialize(i) for i in v]
        elif isinstance(v, float):
            item[k] = Decimal(str(v))
    return item


class DynamoDBLocalStream:
    def __init__(self, table_name):
        self._table_name = table_name
        self._client = boto3.client("dynamodbstreams", endpoint_url="http://localhost:8000")
        self._stream_arn = self._get_stream_arn()
        self._shard_id = self._get_shard_id()
        self._shard_iterator = self._get_shard_iterator()

    def _get_stream_arn(self):
        describe_table_response = dynamodb.meta.client.describe_table(
            TableName=self._table_name)
        return describe_table_response["Table"]["LatestStreamArn"]

    def _get_shard_id(self):
        describe_stream_response =  self._client.describe_stream(
            StreamArn=self._stream_arn)
        return describe_stream_response["StreamDescription"]["Shards"][0]["ShardId"]

    def _get_shard_iterator(self):
        iterator = self._client.get_shard_iterator(
            StreamArn=self._stream_arn,
            ShardId=self._shard_id,
            ShardIteratorType="TRIM_HORIZON",
        )
        return iterator["ShardIterator"]

    def get_records(self):
        records_in_response = self._client.get_records(
            ShardIterator=self._shard_iterator, Limit=100)
        return records_in_response["Records"]
    

class DynamoStreamPoller:
    def __init__(self, table_name, interval=100):
        self._table_name = table_name
        self._stream = DynamoDBLocalStream(table_name)
        self._interval = interval
        self._exit = False


    def poll(self, handlers:Iterable[Callable[[dict,Any], Any]]):
        records = self._stream.get_records()
        while self._exit is False:
            records = self._stream.get_records()
            wait_until = datetime.now() + timedelta(milliseconds=self._interval)
            if len(records) > 0:
                # Invoke lambda handler with the records
                for handler in handlers:
                    try:
                        handler({"Records": records},{})
                        print(f"DynamoDB STREAM: Invoked handler: {handler.__name__}!")
                    except Exception as e:
                        print(f"DynamoDB STREAM: Error invoking {handler.__name__}: {e}")
            
            # sleep until the next poll
            time.sleep((wait_until - datetime.now()).total_seconds())
            

    