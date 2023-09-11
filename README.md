# Cloudly Dev CLI

This is a CLI tool for debugging lambda API locally.


## How to setup

1. Install the CLI tool

### pip
# Install from github
```bash
pip install git+https://github.com/nanaduah1/cloudly-dynamodb.git
```

### poetry
```bash
poetry add git+https://github.com/nanaduah1/cloudly-dynamodb.git
```

2. Create a `Cloudlyfile.yml` file in the root of your project

```bash
poetry run cloudlydev init
```
This will create a `Cloudlyfile.yml` file in the root of your project. Open it and update the `Cloudlyfile.yml` file to match your project.

3. Create VSCode launch configuration

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Debug Cloudly",
      "type": "python",
      "request": "launch",
      "program": "${workspaceFolder}/.venv/bin/cloudlydev",
      "python": "${workspaceFolder}/.venv/bin/python",
      "console": "integratedTerminal",
      "args": ["-c", "runserver"],
      "justMyCode": true
    }
  ]
}
```

NOTE: If you need to use the local DynamoDB database, you should add the environment variables

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Debug Cloudly",
      "type": "python",
      "request": "launch",
      "program": "${workspaceFolder}/.venv/bin/cloudlydev",
      "python": "${workspaceFolder}/.venv/bin/python",
      "console": "integratedTerminal",
      "args": ["-c", "runserver"],
      "justMyCode": true,
      "env": {
        "DYANMODB_ENDPOINT_URL": "http://localhost:8000",
        "AWS_DEFAULT_REGION": "us-east-1",
        "AWS_ACCESS_KEY_ID": "test",
        "AWS_SECRET_ACCESS_KEY": "test",
        "DataTableName": "forkin-table", # This is the name of the table in your local DynamoDB
      }
    }
  ]
}
```

4. Run the debugger


## How to define routes

The route allows you to map your lambda function to a specific path and method. The path can be a static path or a path with a variable. The variable is defined by adding `<variable_name:path>` to the path This is equivalent to `{variable_name}` in AWS API Gateway path variables. The variable name is used as the name of the variable in the lambda function. Example: `/hello/<name:path>` will match `/hello/world` and the value of `name` will be `world`. The `:path` is used to match the entire path. If you want to match a specific part of the path, you can use `:string` or `:int`. Example: `/hello/<name:string>` will match `/hello/world` and the value of `name` will be `world`. Example: `/hello/<name:int>` will match `/hello/123` and the value of `name` will be `123`.

The method is the HTTP method that will be used to match the route. The method can be `GET`, `POST`, `PUT`, `DELETE`, `PATCH`, `OPTIONS`, `HEAD`, `ANY`. The `ANY` method will match all methods.

```ymal
routes:
  - path: /hello/<name:path>
    method: GET
    handler: hello
```
