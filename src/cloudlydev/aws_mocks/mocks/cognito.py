class CognitoIdentityProvider:
    def __init__(self, config):
        self._config = config

    def mock(self, method, **kwargs):
        result = self.Meta.method_responses.get(method, {})
        override_user = self._config.get("user")
        if override_user:
            result = {**result, **override_user}

        return result

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
