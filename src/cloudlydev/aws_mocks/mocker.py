from cloudlydev.aws_mocks.mocks.cognito import CognitoIdentityProvider

mocked = {
    "CognitoIdentityProvider": CognitoIdentityProvider,
}


def mock_for(cls, method, original, config, **kwargs):
    cls_name = cls.__class__.__name__

    if cls_name in mocked:
        return mocked[cls_name](config or {}).mock(method, **kwargs)
    else:
        return original(cls, method, kwargs)
