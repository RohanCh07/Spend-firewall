import json
import math
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ModelPrice:
    model: str
    provider: str
    input: float  # USD per 1M tokens == micro-USD per token
    output: float


class PriceTable:
    def __init__(self, models: dict[str, ModelPrice]):
        self.models = models
        self._by_len = sorted(models, key=len, reverse=True)

    @classmethod
    def load(cls, path: Path) -> "PriceTable":
        raw = json.loads(path.read_text())["models"]
        return cls({m: ModelPrice(m, v["provider"], float(v["input"]), float(v["output"])) for m, v in raw.items()})

    def lookup(self, model: str) -> ModelPrice | None:
        if model in self.models:
            return self.models[model]
        for name in self._by_len:
            if model.startswith(name):
                return self.models[name]
        return None


def cost_micro(price: ModelPrice, input_tokens: int, output_tokens: int) -> int:
    """Cost in integer micro-USD (1e-6 USD), rounded up. Integers keep Redis math exact."""
    return math.ceil(input_tokens * price.input + output_tokens * price.output)


def usd(micro: int) -> float:
    return round(micro / 1_000_000, 6)


def micro(usd_value: float) -> int:
    return round(usd_value * 1_000_000)
