import logging
from abc import ABC, abstractmethod
from typing import Callable, Generic, Iterable, List, Mapping, Type

from llm_c2rust.analyzer.utils import N, P


import logging

logger: logging.Logger = logging.getLogger(__name__)


class Extracter(ABC, Generic[P, N]):
    @abstractmethod
    def extract(self, nodes: Iterable[N]) -> Mapping[Type[P], List[N]]:
        raise NotImplementedError()

    @staticmethod
    def extract_by_predicate(
        nodes: Iterable[N],
        predicate: Callable[[N], bool],
    ) -> List[N]:
        return [child for child in nodes if predicate(child)]

    @staticmethod
    def extract_by_type(nodes: Iterable[N], node_types: List[str]) -> List[N]:
        return Extracter.extract_by_predicate(
            nodes, lambda child: child.type in node_types
        )
