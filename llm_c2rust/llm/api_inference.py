import asyncio
import json
import logging
import time
import traceback
from collections.abc import AsyncGenerator, Callable, Generator, Iterable
from types import CoroutineType
from typing import Any, NamedTuple

import openai
from httpx import RemoteProtocolError
from openai.types.chat.chat_completion import ChatCompletion
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk


from llm_c2rust.llm.lm_inference import (
    AsyncLanguageModelPredictor,
    LanguageModelPredictor,
)


from .uni_tokenizer import UniTokenizer

logger: logging.Logger = logging.getLogger(__name__)


async def retry_forever(
    chat: Callable[[], CoroutineType[Any, Any, str | None]], tokens_num: int
) -> str | None:
    sleep_time = 60

    async def bin_backoff_sleep():
        nonlocal sleep_time
        logger.error(f"Retrying in {sleep_time} seconds")
        await asyncio.sleep(sleep_time)
        sleep_time *= 2

    while True:
        try:
            return await chat()

        except openai.OpenAIError as e:
            if getattr(e, "status_code", None) == 500:
                logger.error(f"OpenAIError: {e}")
                print("tokens num:", tokens_num)
                await bin_backoff_sleep()
                continue
            else:
                raise

        except (RemoteProtocolError, json.JSONDecodeError):
            logger.error(traceback.format_exc())
            print("tokens num:", tokens_num)
            await bin_backoff_sleep()
            continue


class APIInference(LanguageModelPredictor):
    """
    A class for interacting with an LLM API.
    """

    def __init__(
        self, model_name: str, api_key: str, base_url: str = "https://api.openai.com/v1"
    ):
        """
        Initialize the APIInference class.

        :param model_name: The name of the LLM model to use.
        :type model_name: str
        :param api_key: The API key for the LLM API.
        :type api_key: str
        :param base_url: The base URL for the LLM API.
        :type base_url: str
        """
        self.model_name: str = model_name
        self.api_key: str = api_key
        self.base_url: str = base_url
        self.client: openai.OpenAI = openai.OpenAI(
            api_key=self.api_key, base_url=self.base_url
        )
        self.tokenizer = UniTokenizer(self.model_name)

    def __repr__(self) -> str:
        """
        Return a string representation of the APIInference instance.
        """
        return f"APIInference(model_name={self.model_name}, base_url={self.base_url})"

    def token_num(self, text: str | list[dict[str, str]]) -> int:
        """
        Return the number of tokens in the text.

        :param text: The text to count the tokens of, or a list of messages.
        :type text: str

        :return: The number of tokens in the text.
        :rtype: int
        """
        if self.tokenizer is None:
            raise Exception("The tokenizer is None")
        return self.tokenizer.token_num(text=text)

    def chat(
        self,
        messages: list[dict[str, str]],
        max_length: int = 2048,
        temperature: float | None = None,
        top_p: float | None = None,
    ) -> str | None:
        """
        Generate a response from the LLM.

        :param messages: The messages to send to the LLM.
        :type messages: list[dict[str, str]]
        :param max_length: The maximum number of tokens in the response.
        :type max_length: int
        :param temperature: The temperature to use for the response.
        :type temperature: float | None
        :param top_p: The top p to use for the response.
        :type top_p: float | None

        :return: The response from the LLM.
        :rtype: str | None
        """
        outputs = self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,  # type: ignore
            max_tokens=max_length,
            temperature=temperature,
            top_p=top_p,
        )
        return outputs.choices[0].message.content

    def chat_stream(
        self,
        messages: list[dict[str, str]],
        max_length: int = 2048,
        temperature: float | None = None,
        top_p: float | None = None,
    ) -> Generator[str | None, None, None]:
        """
        Generate a stream of responses from the LLM.

        :param messages: The messages to send to the LLM.
        :type messages: list[dict[str, str]]
        :param max_length: The maximum number of tokens in the response.
        :type max_length: int, optional
        :param temperature: The temperature to use for the response.
        :type temperature: float, optional
        :param top_p: The top p to use for the response.
        :type top_p: float, optional

        :return: A generator of the response from the LLM.
        :rtype: Generator[str | None, None, None]
        """
        response: openai.Stream[ChatCompletionChunk] = (
            self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,  # type: ignore
                max_tokens=max_length,
                temperature=temperature,
                top_p=top_p,
                stream=True,
            )
        )
        for chunk in response:
            yield chunk.choices[0].delta.content


class Record(NamedTuple):
    token_num: int
    timestamp: float


def enforce_trailing_slash(url: str) -> str:
    """
    Enforce a trailing slash on a URL.

    Args:
        url: The URL to enforce a trailing slash on.

    Returns:
        The URL with a trailing slash.
    """
    if url.endswith("/"):
        return url
    return url + "/"


class AsyncAPIInference(AsyncLanguageModelPredictor):
    """
    A class for interacting with an LLM async API for a specific model.
    """

    def __init__(
        self,
        model_name: str,
        base_url: str,
        api_keys: Iterable[str],
        qpm: int | None,
        tpm: int | None,
        default_max_tokens: int,
        reasoning: bool,
    ):
        """
        Initialize the APIInference class.

        Args:
            model_name: The name of the LLM model to use.
            api_key: The API key for the LLM API.
            base_url: The base URL for the LLM API.
        """
        self.model_name = model_name
        self.base_url = enforce_trailing_slash(base_url)
        self.api_keys = list(api_keys)
        self.qpm = qpm
        self.tpm = tpm
        self.history: list[Record] = []

        self.clients = [
            openai.AsyncOpenAI(api_key=api_key, base_url=base_url)
            for api_key in api_keys
        ]
        self.tokenizer = UniTokenizer(self.model_name)
        self.default_max_tokens = default_max_tokens
        self.reasoning = reasoning

    def __repr__(self) -> str:
        """
        Return a string representation of the AsyncAPIInference instance.
        """
        return f"AsyncAPIInference(model_name={self.model_name})"

    def token_num(self, text: str | list[dict[str, str]]) -> int:
        """
        Return the number of tokens in the text.

        Args:
            text: The text to count the tokens of, or a list of messages.

        Returns:
            The number of tokens in the text.
        """
        if self.tokenizer is None:
            raise Exception("The tokenizer is None")
        return self.tokenizer.token_num(text=text)

    def wait_time(self, messages: list[dict[str, str]], max_tokens: int) -> float:

        current_time = time.time()
        # check if query times exceed
        if self.qpm and len(self.history) >= self.qpm:
            delta = current_time - self.history[-self.qpm].timestamp
            if delta <= 60:
                return 60 - delta
        if self.tpm is None:
            return 0
        token_num_sum = self.token_num(messages) + max_tokens
        for record in reversed(self.history):
            delta = current_time - record.timestamp
            if delta > 60:
                break
            token_num_sum += record.token_num
            if token_num_sum >= self.tpm:
                return 60 - delta
        return 0

    async def ready_to_go(
        self, messages: list[dict[str, str]], max_tokens: int | None = None
    ) -> None:
        if max_tokens is None:
            max_tokens = self.default_max_tokens
        while (wait_time := self.wait_time(messages, max_tokens)) > 0:
            await asyncio.sleep(wait_time)
        self.history.append(
            Record(
                token_num=self.token_num(messages) + max_tokens, timestamp=time.time()
            )
        )

    async def _chat_under_limit(
        self,
        client: openai.AsyncOpenAI,
        messages: list[dict[str, str]],
        max_tokens: int | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
    ):
        await self.ready_to_go(messages, max_tokens)
        if self.model_name.startswith("doubao"):
            extra_body = {
                "thinking": {
                    "type": "disabled",
                }
            }
        else:
            extra_body = {}
        outputs: ChatCompletion = await client.chat.completions.create(
            model=self.model_name,
            messages=messages,  # type:ignore
            temperature=temperature,
            top_p=top_p,
            extra_body=extra_body,
        )
        return outputs.choices[0].message.content

    async def _chat(
        self,
        messages: list[dict[str, str]],
        max_tokens: int | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
    ) -> str | None:

        for client in self.clients:
            try:
                return await retry_forever(
                    lambda: self._chat_under_limit(
                        client, messages, max_tokens, temperature, top_p
                    ),
                    self.token_num(messages),
                )
            except Exception as e:
                logger.error(traceback.format_exc())
                continue

    async def chat(
        self,
        messages: list[dict[str, str]],
        max_tokens: int | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
    ) -> str | None:
        """
        Async version - Generate a response from the LLM.

        Args:
            messages: The messages to send to the LLM.
            max_length: The maximum number of tokens in the response.
            temperature: The temperature to use for the response.
            top_p: The top p to use for the response.

        Returns:
            The response from the LLM.
        """
        for client in self.clients:
            if self.reasoning:
                return await retry_forever(
                    lambda: self._chat_stream_under_limit(
                        client, messages, max_tokens, temperature, top_p
                    ),
                    self.token_num(messages),
                )
            else:
                return await retry_forever(
                    lambda: self._chat_under_limit(
                        client, messages, max_tokens, temperature, top_p
                    ),
                    self.token_num(messages),
                )

    async def _chat_stream_under_limit(
        self,
        client: openai.AsyncOpenAI,
        messages: list[dict[str, str]],
        max_tokens: int | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
    ) -> str | None:
        await self.ready_to_go(messages, max_tokens)
        if self.model_name.startswith("doubao"):
            extra_body = {
                "thinking": {
                    "type": "disabled",
                }
            }
        else:
            extra_body = {}
        response: openai.AsyncStream[ChatCompletionChunk] = (
            await client.chat.completions.create(
                model=self.model_name,
                messages=messages,  # type:ignore
                temperature=temperature,
                top_p=top_p,
                stream=True,
                extra_body=extra_body,
            )
        )
        res = ""
        async for chunk in response:
            content = chunk.choices[0].delta.content
            if content is None:
                continue
            res += content
        return res

    async def chat_stream(
        self,
        messages: list[dict[str, str]],
        max_tokens: int | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
    ) -> AsyncGenerator[str, None]:
        """
        Async version - Generate a stream of responses from the LLM.

        Args:
            messages: The messages to send to the LLM.
            max_length: The maximum number of tokens in the response.
            temperature: The temperature to use for the response.
            top_p: The top p to use for the response.

        Returns:
            A generator of the response from the LLM.
        """

        for client in self.clients:

            await self.ready_to_go(messages, max_tokens)

            response: openai.AsyncStream[ChatCompletionChunk] = (
                await client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,  # type:ignore
                    max_completion_tokens=max_tokens,
                    temperature=temperature,
                    top_p=top_p,
                    stream=True,
                )
            )

            async for chunk in response:
                content = chunk.choices[0].delta.content
                if content is None:
                    continue
                yield content
            return
