from abc import ABC, abstractmethod
from typing import AsyncGenerator, Dict, Generator, List, Optional, Union

from llm_c2rust.llm.uni_tokenizer import UniTokenizer


class LanguageModelPredictor(ABC):
    def __init__(
        self,
    ) -> None:
        self.tokenizer: Optional[UniTokenizer] = None

    @abstractmethod
    def token_num(self, text: Union[str, List[Dict[str, str]]]) -> int:
        """
        Calculate the number of tokens in the text.

        Args:
            text: The text to calculate the number of tokens.

        Returns:
            The number of tokens in the text.
        """
        raise NotImplementedError()

    @abstractmethod
    def chat(
        self,
        messages: List[Dict[str, str]],
        max_length: int = 2048,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
    ) -> Optional[str]:
        """
        Chat with the language model.

        Args:
            messages: The messages to chat with the language model.
            max_length: The maximum length of the generated text.
            temperature: The temperature of the language model.
            top_p: The top p of the language model.

        Returns:
            The generated text.
        """
        raise NotImplementedError()

    @abstractmethod
    def chat_stream(
        self,
        messages: List[Dict[str, str]],
        max_length: int = 2048,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
    ) -> Generator[Optional[str], None, None]:
        """
        Chat with the language model in a streaming manner.

        Args:
            messages: The messages to chat with the language model.
            max_length: The maximum length of the generated text.
            temperature: The temperature of the language model.
            top_p: The top p of the language model.

        Returns:
            A generator of the generated text.
        """
        raise NotImplementedError()


class AsyncLanguageModelPredictor(ABC):
    def __init__(self, rate_limit=1) -> None:
        self.tokenizer: Optional[UniTokenizer] = None
        self.rate_limit = rate_limit

    @abstractmethod
    def token_num(self, text: Union[str, List[Dict[str, str]]]) -> int:
        """
        Calculate the number of tokens in the text.

        Args:
            text: The text to calculate the number of tokens.

        Returns:
            The number of tokens in the text.
        """
        raise NotImplementedError()

    @abstractmethod
    async def chat(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 2048,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
    ) -> Optional[str]:
        """
        Chat with the language model.

        Args:
            messages: The messages to chat with the language model.
            max_length: The maximum length of the generated text.
            temperature: The temperature of the language model.
            top_p: The top p of the language model.

        Returns:
            The generated text.
        """
        raise NotImplementedError()

    @abstractmethod
    async def chat_stream(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 2048,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
    ) -> AsyncGenerator[Optional[str], None]:
        """
        Generate a stream of responses from the language model.

        Args:
            messages: The messages to send to the language model.
            max_length: The maximum number of tokens in the response.
            temperature: The temperature to use for the response.
            top_p: The top p to use for the response.

        Returns:
            A generator of the response from the language model.
        """
        yield  # type: ignore[misc]
        raise NotImplementedError()
