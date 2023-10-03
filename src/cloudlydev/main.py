from collections import defaultdict
import os
import sys
from unittest.mock import patch
import yaml
import importlib
import botocore
from threading import Thread
from argparse import ArgumentParser

from bottle import request, run, Bottle, response
from cloudlydev.aws_mocks.mocker import mock_for
from cloudlydev.dynamodb import DynamoStreamPoller
from cloudlydev.cron import LambdaCronRunner


def _parse_config(config_path):
    if os.path.exists(config_path):
        with open(config_path) as f:
            return yaml.safe_load(f)
    return {}


class LambdaImporter:
    def load_handler(self, config, root="lambdas", python_version="3.11"):
        handler = config.get("handler") or self.Meta.default_handler
        function_path = config["path"]
        project_name = os.path.basename(function_path)
        python_version = config.get("python_version") or python_version

        module_name, func_name = handler.split(".")
        handler_module_path = os.path.join(
            root, function_path, project_name.lower(), module_name + ".py"
        )

        package_name = os.path.basename(os.path.dirname(handler_module_path))
        package = os.path.abspath(os.path.dirname(handler_module_path))

        if package not in sys.path:
            sys.path.insert(0, package)

        if os.path.dirname(package) not in sys.path:
            sys.path.insert(0, os.path.dirname(package))

        # We shoud also add the venv site-packages to the path
        venv = config.get("venv")
        if not venv:
            venv = os.path.join(
                os.path.dirname(package),
                ".venv",
                "lib",
                f"python{python_version}",
                "site-packages",
            )

        if os.path.exists(venv) and venv not in sys.path:
            sys.path.insert(0, venv)

        importlib.invalidate_caches()
        module_qualname = f"{package_name}.{module_name}"
        module = importlib.import_module(module_qualname, package=package)
        fn = getattr(module, func_name)

        return fn

    class Meta:
        default_handler = "handler.handler"


class DevServer:
    def __init__(self, **kwargs):
        self._host = kwargs["host"]
        self._port = kwargs["port"]
        self._config = _parse_config(kwargs["config"])
        self._app = Bottle()

        self._old_path = sys.path
        self._old_modules = sys.modules

        try:
            # map routes
            lambda_importer = LambdaImporter()
            print("Mapping routes... from ", kwargs["config"])
            for route in self._config["routes"]:
                http_method = route.get("method", "GET")
                handler = lambda_importer.load_handler(
                    route,
                    root=self._config["root"],
                    python_version=self._config.get("python_version", "3.11"),
                )
                self._app.route(
                    route["url"],
                    method=(http_method, "OPTIONS"),
                    callback=self._bind_to_lambda(handler),
                )
                print(f"Mapped {http_method} {route['url']} to {handler.__name__}")
        except Exception as e:
            print("ERROR", e)

    def run(self):
        self._app.route("/", "GET", self.handle_request)
        self._start_dynamodb_stream()
        self._start_cron_jobs()
        run(self._app, host=self._host, port=self._port, debug=True, reloader=True)

    def _start_cron_jobs(self):
        cron = self._config.get("cron", [])
        if not cron:
            return

        # Group cron jobs by interval
        cron_jobs_by_interval = defaultdict(list)
        for job in cron:
            cron_jobs_by_interval[job.get("interval", "1m")].append(job)

        for interval, jobs in cron_jobs_by_interval.items():
            cron_jobs = []
            for job in jobs:
                py_version = job.get("python_version", "3.11") or self._config.get(
                    "python_version", "3.11"
                )

                try:
                    print(f"Binding {job['path']} to cron job")
                    handler = LambdaImporter().load_handler(
                        job,
                        root=self._config["root"],
                        python_version=py_version,
                    )
                    cron_jobs.append(handler)
                except Exception as e:
                    print(f"ERROR: {job['path']} failed to load", e)

            if not cron_jobs:
                continue

            # Run in a new thread
            cron_runner = LambdaCronRunner(handlers=cron_jobs, interval=interval)
            thread = Thread(target=cron_runner.start)
            thread.start()

    def _start_dynamodb_stream(self):
        table = self._config.get("table")
        if not table or not table.get("stream"):
            return

        stream_config = table["stream"]
        if not stream_config.get("enabled"):
            return

        bindings = stream_config.get("bindings", [])
        if not bindings:
            return

        bound_handlers = []
        for binding in bindings:
            py_version = binding.get("python_version", "3.11") or self._config.get(
                "python_version", "3.11"
            )

            try:
                print(f"Binding {binding['path']} to DynamoDB stream")
                handler = LambdaImporter().load_handler(
                    binding,
                    root=self._config["root"],
                    python_version=py_version,
                )
                bound_handlers.append(handler)
            except Exception as e:
                print(f"ERROR: {binding['path']} failed to load", e)

        if not bound_handlers:
            return

        poller = DynamoStreamPoller(table["name"])

        # Run in a new thread
        thread = Thread(target=poller.poll, args=(bound_handlers,))
        thread.start()

    def handle_request(self, *args, **kwargs):
        return (
            "<html><body><h1>Cloudlydev</h1><p>Cloudlydev is running</p></body></html>"
        )

    def _handle_cors_request(self, *args, **kwargs):
        self._set_common_headers_()
        return ""

    def _set_common_headers_(self):
        response.set_header("Server", "Cloudly Dev Server")
        response.set_header("Access-Control-Allow-Origin", "*")
        response.set_header("Access-Control-Allow-Headers", "*")
        response.set_header("Access-Control-Allow-Methods", "*")
        response.set_header("Access-Control-Allow-Credentials", "true")
        response.set_header("Access-Control-Max-Age", "86400")
        response.set_header("Access-Control-Expose-Headers", "*")
        response.set_header("Vary", "Origin")
        response.set_header("Vary", "Access-Control-Request-Method")
        response.set_header("Vary", "Access-Control-Request-Headers")
        response.set_header("Content-Type", "application/json")

    def _bind_to_lambda(self, handler):
        this = self

        # We need to keep a reference to the original make_api_call
        # so we can call it from our mock for cases where we don't want to mock
        original_make_api_call = botocore.client.BaseClient._make_api_call

        def mock_api_call(self, operation_name, kwarg):
            return mock_for(
                self,
                operation_name,
                original_make_api_call,
                config=this._config,
                **kwarg,
            )

        # This intercepts all calls to boto3 and replaces them with our mock
        @patch("botocore.client.BaseClient._make_api_call", new=mock_api_call)
        def _handler(*args, **kwargs):
            if request.method == "OPTIONS":
                return self._handle_cors_request(*args, **kwargs)

            user = self._config.get("user", {})
            body = request.body.read().decode("utf-8")
            event = {
                "path": request.path,
                "httpMethod": request.method,
                "headers": {k.lower(): v for k, v in dict(request.headers).items()},
                "queryStringParameters": dict(request.query),
                "pathParameters": {**kwargs},
                "requestContext": {
                    "authorizer": {
                        "jwt": {
                            "claims": {
                                "cognito:groups": f'[{" ".join(user.get("groups", []))}]',
                                "username": user.get("username"),
                                "client_id": self._config.get(
                                    "client_id", "testclientid"
                                ),
                            }
                        }
                    },
                    "accountId": "123456789012",
                    "http": {"sourceIp": request.remote_addr},
                    "path": request.path,
                },
            }

            if body:
                event["body"] = body

            results = handler(event, {})
            status_code = results.get("statusCode", 200)
            response.status = status_code

            self._set_common_headers_()
            for k, v in results.get("headers", {}).items():
                response.headers.append(k, v)

            return results["body"]

        return _handler

    def __enter__(self):
        import sys

        sys.modules = self._old_modules.copy()
        sys.path = sys.path[:]
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        sys.path = self._old_path
        sys.modules = self._old_modules


def build_args(parser: ArgumentParser):
    parser.add_argument(
        "-c",
        type=str,
        default="runserver",
        dest="command",
        choices=[
            "runserver",
            "initdb",
            "loaddata",
            "initlambda",
            "init",
        ],
    )
    parser.add_argument("--host", type=str, default="localhost")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--config", type=str, default="Cloudlyfile.yml")
    parser.add_argument("--table", type=str, default="")
    parser.add_argument("--file", type=str, default="data.yml")
    parser.add_argument("--force", type=bool, default=False)

    return parser.parse_args()


def initialize_lambdas(config):
    """
    Run poetry install in each lambda folder based on all the registered lambdas
    """

    # Change poetry to use local venvs
    os.system("poetry config virtualenvs.in-project true")
    root = os.path.abspath(config["root"])
    all_lambdas = (
        config["routes"]
        + config.get("cron", [])
        + config.get("stream", {}).get("bindings", [])
    )

    for route in all_lambdas:
        lambda_path = os.path.join(root, route["path"])
        if os.path.exists(lambda_path):
            print(f"Initializing lambda {lambda_path}")
            os.chdir(lambda_path)
            os.system("poetry update")
            print("Done!")
        else:
            print(f"Lambda path {lambda_path} does not exist")


def init(**kwargs):
    sample_config = """
    root: lambdas # root folder for lambdas (required)
    python: 3.11 # python version to use (default 3.11)
    routes:
      - path: hello/hello # path to lambda handler relative to root (required)
        url: /hello # url to map to lambda (required)
        method: GET # http method to map to default GET
        handler: handler.handler # handler to map to (default handler.handler)
        # venv: full/path/to/.venv # optional (default path/../.venv)

    """

    # Create sample config file if it doesn't exist
    if not os.path.exists(kwargs["config"]):
        with open(kwargs["config"], "w") as f:
            f.write(sample_config)
            print(f"Created sample config file at {kwargs['config']}")
    else:
        print(f"Config file already exists at {kwargs['config']}")


def main():
    parser = ArgumentParser(
        prog="cloudlydev", description="CLI for cloudly development with AWS lambda"
    )
    args = build_args(parser)

    if args.command == "init":
        init(**vars(args))
    elif args.command == "runserver":
        with DevServer(**vars(args)) as s:
            try:
                s.run()
            except KeyboardInterrupt:
                print("Exiting...")
    elif args.command == "initdb":
        from cloudlydev.dynamodb import reset_db

        reset_db(_parse_config(args.config), force=args.force)
    elif args.command == "loaddata":
        from cloudlydev.dynamodb import load_data

        print(f"Loading data from {args.file} into {args.table}")
        data = _parse_config(args.file)
        load_data(args.table, data.get("records", []))
        print("Done!")

    elif args.command == "initlambda":
        initialize_lambdas(_parse_config(args.config))
    else:
        print(f"Unknown command {args.command}")


if __name__ == "__main__":
    main()
