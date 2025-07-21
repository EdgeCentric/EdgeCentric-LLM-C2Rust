from abc import ABC, abstractmethod
from collections.abc import Iterable
import logging
from typing import TYPE_CHECKING

from llm_c2rust.llm.LLM import Agent
from llm_c2rust.core.transpilation_workspace import TranslationWorkspace
from llm_c2rust.llm.api_inference import AsyncAPIInference
from llm_c2rust.llm.uni_tokenizer import UniTokenizer
from llm_c2rust.segmenter.code_segment import CodeSegment
from llm_c2rust.segmenter.segmenter import Segmenter

if TYPE_CHECKING:
    from llm_c2rust.core.transpiler import ProjectTranspiler


logger = logging.getLogger(__name__)


# just a wrapper of interactly translating
class InteractEngine(ABC):
    temperature: float

    def __init__(
        self,
        segmenter: Segmenter,
        pedicator: AsyncAPIInference,
        token_num: int,
        token_num_method: str,
        temperature: float,
    ):
        self.segmenter = segmenter

        self.max_source_tokens = token_num
        self.tokenizer = UniTokenizer(token_num_method)
        self.temperature = temperature

    @property
    @abstractmethod
    def agent(self) -> Agent:
        raise NotImplementedError()

    @abstractmethod
    def describe(self) -> str:
        raise NotImplementedError()

    @abstractmethod
    async def trans_project(self, project: "ProjectTranspiler") -> None:
        raise NotImplementedError()

    _project: "ProjectTranspiler"

    def _get_segments(self) -> Iterable[CodeSegment]:
        logger.info("generating slices, waiting...")
        segments = self.segmenter.segment()

        return segments

    @property
    @abstractmethod
    def workspace(self) -> TranslationWorkspace:
        raise NotImplementedError()
