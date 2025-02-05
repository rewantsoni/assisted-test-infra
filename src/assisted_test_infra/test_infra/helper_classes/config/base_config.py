from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from typing import Any, Dict, Tuple

from service_client import log


class Triggerable(ABC):
    def trigger(self, triggers: Dict[Tuple[Tuple[str, Any]], Dict[str, Any]]):
        for conditions, values in triggers.items():
            assert isinstance(conditions, tuple) and all(
                isinstance(condition, tuple) for condition in conditions
            ), f"Key {conditions} must be tuple of tuples"

            if all(self._is_set(param, expected_value) for param, expected_value in conditions):
                self._handle_trigger(conditions, values)

    def _is_set(self, var, expected_value):
        return getattr(self, var, None) == expected_value

    def _handle_trigger(self, conditions: Tuple[Tuple[str, Any]], values: Dict[str, Any]) -> None:
        for k, v in values.items():
            self._set(k, v)
        log.info(f"{conditions} is triggered. Updating global variables: {values}")

    @abstractmethod
    def _set(self, key: str, value: Any):
        pass


@dataclass
class _BaseConfig(Triggerable, ABC):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def __post_init__(self):
        """
        Set all variables to its default value
        Assuming key on target dict (where get_default get it's values from)
        """
        for k, v in self.get_all().items():
            if v is None:
                setattr(self, k, self.get_default(k))

    @classmethod
    def get_annotations(cls):
        """Get attributes with annotations - same as obj.__annotations__ but recursive"""

        annotations = {}
        for c in cls.mro():
            try:
                annotations.update(**c.__annotations__)
            except AttributeError:
                # object, at least, has no __annotations__ attribute.
                pass
        return annotations

    @staticmethod
    @abstractmethod
    def get_default(key, default=None) -> Any:
        pass

    def get_copy(self):
        return self.__class__(**self.get_all())

    def get_all(self) -> dict:
        return asdict(self)

    def _set(self, key: str, value: Any):
        if hasattr(self, key):
            self.__setattr__(key, value)

    def set_value(self, attr: str, new_val):
        setattr(self, attr, self._get_correct_value(attr, new_val))

    def _get_correct_value(self, attr: str, new_val):
        """Get value in it's correct type"""
        annotations = self.get_annotations()
        if not hasattr(self, attr):
            raise AttributeError(f"Can't find {attr} among {annotations}")

        _type = annotations[attr]

        if hasattr(_type, "__origin__"):
            return _type.__origin__([new_val])

        # str, int, float, bool, Path, and more
        return new_val if isinstance(new_val, _type) else _type(new_val)
