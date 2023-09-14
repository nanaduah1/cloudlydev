class CognitoIdentityProvider:
    def __init__(self, config):
        self._config = config

    def mock(self, method, **kwargs):
        return self.Meta.method_responses.get(method, {})

    class Meta:
        method_responses = {
            "GetUser": {
                "UserAttributes": [],
                "Username": "testuser",
                "UserStatus": "CONFIRMED",
            },
            "AdminCreateUser": {
                "User": {
                    "Username": "testuser",
                    "UserStatus": "CONFIRMED",
                    "UserAttributes": [],
                }
            },
            "AdminAddUserToGroup": {},
        }
