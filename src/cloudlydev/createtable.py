import boto3


def reset_db(config):
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

    dynamodb = boto3.resource("dynamodb", endpoint_url="http://localhost:8000")
    try_delete_db(dynamodb, table_def["name"])

    print(f"Creating table {table_def['name']}")
    dynamodb.create_table(
        TableName=table_def["name"],
        KeySchema=key_schema,
        AttributeDefinitions=attr_defs,
        BillingMode="PAY_PER_REQUEST",
        GlobalSecondaryIndexes=indexes,
    )


def try_delete_db(client, table_name):
    print(f"Deleting table {table_name}")
    dynamodb = client
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
