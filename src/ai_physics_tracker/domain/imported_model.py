"""工程受管的教师模型；自检不是训练履历，也不证明科学准确性。"""

from dataclasses import dataclass, field
import hashlib
import json
from uuid import UUID

from ai_physics_tracker.domain.types import JsonObject

MODEL_FILES = ("config.yaml", "pytorch_config.yaml", "checkpoint.pt")


@dataclass(frozen=True)
class ImportedModel:
    model_id: UUID
    name: str
    bodyparts: tuple[str, ...]
    sha256: dict[str, str]
    self_test: JsonObject = field(default_factory=dict)
    extra_fields: JsonObject = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.model_id, UUID) or not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("Imported model needs an id and name")
        if (not self.bodyparts or any(not isinstance(b, str) or not b.strip() for b in self.bodyparts)
                or len(set(self.bodyparts)) != len(self.bodyparts)):
            raise ValueError("Model bodyparts must be nonempty unique names")
        if set(self.sha256) != set(MODEL_FILES) or any(
            not isinstance(h, str) or len(h) != 64 or any(c not in "0123456789abcdef" for c in h)
            for h in self.sha256.values()
        ):
            raise ValueError("Model manifest needs SHA256 for all three files")
        if not isinstance(self.self_test, dict) or not isinstance(self.extra_fields, dict):
            raise ValueError("Model evidence/extra fields must be objects")
        json.dumps([self.self_test, self.extra_fields], allow_nan=False)

    @property
    def manifest_hash(self) -> str:
        value = json.dumps([self.bodyparts, self.sha256], sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(value.encode()).hexdigest()

    @property
    def directory(self) -> str:
        return f"models/{self.model_id}"
