from cloudly.http.decorators import http_api

from stuff.doit import DoIt


@http_api(DoIt())
def handler(event, context):
    pass
