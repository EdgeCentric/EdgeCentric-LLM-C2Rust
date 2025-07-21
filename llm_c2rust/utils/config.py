from typing import Literal

from pydantic import BaseModel


class Endpoint(BaseModel):
    name: str
    proxy: str = ""
    base_url: str
    api_keys: list[str]
    qpm: int | None = None
    tpm: int | None = None
    model: str
    provider: Literal["openai"] = "openai"
    api_type: Literal["chat", "embedding"] = "chat"
    max_tokens: int = 8192
    reasoning: bool = False


class Config(BaseModel):
    endpoints: list[Endpoint]
    token_num: int = 4096
    token_num_method: str = "deepseek-chat"
    max_resolve_round: int = 5
    max_retry: int = 2
