import os
from pathlib import Path

from dotenv import dotenv_values


class EnvironmentCredentialProvider:
    def __init__(self, env_file: str | Path = ".env"):
        self.env_file = Path(env_file)

    def get(self, variable_name: str) -> str | None:
        environment_value = os.getenv(variable_name)
        if environment_value:
            return environment_value
        file_value = dotenv_values(self.env_file).get(variable_name)
        return str(file_value) if file_value else None
