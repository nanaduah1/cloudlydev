import os
import sys
import yaml
import importlib
from argparse import ArgumentParser

from bottle import request, run, Bottle, response


class LambdaImporter:
    def load_handler(self, config, root="lambdas", python_version="3.11"):
        handler = config["handler"]
        function_path = config["path"]
        python_version = config.get("python_version", python_version)
        module_name, func_name = handler.split(".")
        package = os.path.abspath(
            os.path.dirname(os.path.join(root, function_path, module_name + ".py"))
        )
        sys.path.insert(0, package)
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

        if os.path.exists(venv):
            sys.path.insert(0, venv)

        module = importlib.import_module(module_name, package=package)
        return getattr(module, func_name)


class DevServer:
    def __init__(self, **kwargs):
        self._host = kwargs["host"]
        self._port = kwargs["port"]
        self._config = self._parse_config(kwargs["config"])
        self._app = Bottle()

        self._old_path = sys.path
        self._old_modules = sys.modules

        try:
            # map routes
            lambda_importer = LambdaImporter()
            print("Mapping routes... from ", kwargs["config"])
            for route in self._config["routes"]:
                handler = lambda_importer.load_handler(
                    route,
                    root=self._config["root"],
                    python_version=self._config.get("python_version", "3.11"),
                )
                self._app.route(
                    route["url"],
                    method=(route["method"], "OPTIONS"),
                    callback=self._bind_to_lambda(handler),
                )
                print(f"Mapped {route['method']} {route['url']} to {route['handler']}")
        except Exception as e:
            print("ERROR", e)

    def run(self):
        self._app.route("/", "GET", self.handle_request)
        run(self._app, host=self._host, port=self._port, debug=True, reloader=True)

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
        def _handler(*args, **kwargs):
            if request.method == "OPTIONS":
                return self._handle_cors_request(*args, **kwargs)

            body = request.body.read().decode("utf-8")
            event = {
                "path": request.path,
                "httpMethod": request.method,
                "headers": dict(request.headers),
                "queryStringParameters": dict(request.query),
                "body": body,
                "pathParameters": {**kwargs},
            }

            results = handler(event, {})
            status_code = results.get("statusCode", 200)
            response.status = status_code

            self._set_common_headers_()
            for k, v in results.get("headers", {}).items():
                response.headers.append(k, v)

            return (results["body"],)

        return _handler

    def _parse_config(self, config_path):
        if os.path.exists(config_path):
            with open(config_path) as f:
                return yaml.safe_load(f)
        return {}

    def __enter__(self):
        import sys

        sys.modules = self._old_modules.copy()
        sys.path = sys.path[:]
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        sys.path = self._old_path
        sys.modules = self._old_modules


def build_args(parser: ArgumentParser):
    parser.add_argument("-c", type=str, default="runserver", dest="command")
    parser.add_argument("--host", type=str, default="localhost")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--config", type=str, default="Cloudlyfile.yml")
    return parser.parse_args()


def create_config(**kwargs):
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

    with open(kwargs["config"], "w") as f:
        f.write(sample_config)
        print(f"Created sample config file at {kwargs['config']}")


def main():
    parser = ArgumentParser(
        prog="cloudlydev", description="CLI for cloudly development with AWS lambda"
    )
    args = build_args(parser)

    if args.command == "init":
        create_config(**vars(args))
    elif args.command == "runserver":
        with DevServer(**vars(args)) as s:
            try:
                s.run()
            except KeyboardInterrupt:
                print("Exiting...")
    else:
        print(f"Unknown command {args.command}")


if __name__ == "__main__":
    main()
