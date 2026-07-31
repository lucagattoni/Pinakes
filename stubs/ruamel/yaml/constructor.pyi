from ruamel.yaml.error import YAMLError
from ruamel.yaml.scalarbool import ScalarBoolean as ScalarBoolean

class DuplicateKeyError(YAMLError):
    problem: str | None
