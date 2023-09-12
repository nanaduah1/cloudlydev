from dataclasses import dataclass
from flowfast.step import Step


@dataclass
class DoIt(Step):
    name: str = "Hello man!"

    def process(self, data):
        return {**data, "app": self.name}
