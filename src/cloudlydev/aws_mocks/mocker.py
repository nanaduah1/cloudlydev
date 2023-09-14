import botocore
from cloudlydev.aws_mocks.mocks.cognito import CognitoIdentityProvider

mocked = {botocore.client.CognitoIdentityProvider: CognitoIdentityProvider}


def mock_for(cls, method, kwargs):
    if cls in mocked:
        return mocked[cls](kwargs.get("dev_config", {})).mock(method, **kwargs)
    else:
        return {}
