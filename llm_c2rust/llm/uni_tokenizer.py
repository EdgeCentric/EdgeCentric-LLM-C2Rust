import logging
import os
from typing import Any, Dict, List, Optional, Tuple, Union

import tiktoken
import transformers
from transformers.tokenization_utils_base import BatchEncoding, TruncationStrategy
from transformers.utils import PaddingStrategy, TensorType


import logging

logger: logging.Logger = logging.getLogger(__name__)

# Define type aliases and NamedTuples
TextInput = str
PreTokenizedInput = List[str]
EncodedInput = List[int]
TextInputPair = Tuple[str, str]
PreTokenizedInputPair = Tuple[List[str], List[str]]
EncodedInputPair = Tuple[List[int], List[int]]


def openai_num_tokens_from_messages(
    messages: List[Dict[str, str]], model="gpt-4o-mini-2024-07-18"
) -> int:
    """Return the number of tokens used by a list of messages."""
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        logger.warning("Warning: model not found. Using o200k_base encoding.")
        encoding = tiktoken.get_encoding("o200k_base")
    if model in {
        "gpt-3.5-turbo-0125",
        "gpt-4-0314",
        "gpt-4-32k-0314",
        "gpt-4-0613",
        "gpt-4-32k-0613",
        "gpt-4o-mini-2024-07-18",
        "gpt-4o-2024-08-06",
    }:
        tokens_per_message = 3
        tokens_per_name = 1
    elif "gpt-3.5-turbo" in model:
        logger.warning(
            "Warning: gpt-3.5-turbo may update over time. Returning num tokens assuming gpt-3.5-turbo-0125."
        )
        return openai_num_tokens_from_messages(messages, model="gpt-3.5-turbo-0125")
    elif "gpt-4o-mini" in model:
        logger.warning(
            "Warning: gpt-4o-mini may update over time. Returning num tokens assuming gpt-4o-mini-2024-07-18."
        )
        return openai_num_tokens_from_messages(messages, model="gpt-4o-mini-2024-07-18")
    elif "gpt-4o" in model:
        logger.warning(
            "Warning: gpt-4o and gpt-4o-mini may update over time. Returning num tokens assuming gpt-4o-2024-08-06."
        )
        return openai_num_tokens_from_messages(messages, model="gpt-4o-2024-08-06")
    elif "gpt-4" in model:
        logger.warning(
            "Warning: gpt-4 may update over time. Returning num tokens assuming gpt-4-0613."
        )
        return openai_num_tokens_from_messages(messages, model="gpt-4-0613")
    else:
        raise NotImplementedError(
            f"""openai_num_tokens_from_messages() is not implemented for model {model}."""
        )
    num_tokens = 0
    for message in messages:
        num_tokens += tokens_per_message
        for key, value in message.items():
            num_tokens += len(encoding.encode(value))
            if key == "name":
                num_tokens += tokens_per_name
    num_tokens += 3  # every reply is primed with <|start|>assistant<|message|>
    return num_tokens


OPENAI_MODELS = [
    "gpt-3.5-turbo",
    "gpt-3.5-turbo-0125",
    "gpt-3.5-turbo-0613",
    "gpt-3.5-turbo-1106",
    "gpt-3.5-turbo-16k",
    "gpt-3.5-turbo-16k-0613",
    "gpt-4",
    "gpt-4-0314",
    "gpt-4-32k-0314",
    "gpt-4-0613",
    "gpt-4-32k-0613",
    "gpt-4o",
    "gpt-4o-mini-2024-07-18",
    "gpt-4o-2024-08-06",
    "o1-mini",
    "o1-mini-2024-09-12",
    "o1-preview",
    "o1-preview-2024-09-12",
]


DEEPSEEK_MODELS = [
    "deepseek-chat",
    "deepseek-coder",
    "deepseek-v3",
    "deepseek-r1",
    "deepseek-reasoner",
    "deepseek-v3-241226",
    "deepseek-r1-distill-llama-70b",
    "doubao-seed-1-6-250615",
]


class UniTokenizer(object):
    def __init__(self, model: str) -> None:
        self.model = model
        if not os.path.exists(model):
            if self.model.lower() in OPENAI_MODELS:
                self.tokenizer = tiktoken.encoding_for_model(self.model)
            elif self.model.lower() in DEEPSEEK_MODELS:
                self.tokenizer = transformers.AutoTokenizer.from_pretrained(
                    "deepseek-ai/DeepSeek-V2-Lite",
                    revison="604d5664dddd88a0433dbae533b7fe9472482de0",
                )
            elif (
                "qwen-max" in self.model.lower()
                or "qwen-plus" in self.model.lower()
                or "qwen2" in self.model.lower()
            ):
                self.tokenizer = transformers.AutoTokenizer.from_pretrained(
                    "Qwen/Qwen2-7B-Instruct",
                    revison="f2826a00ceef68f0f2b946d945ecc0477ce4450c",
                )
            elif "qwen2.5" in self.model.lower():
                self.tokenizer = transformers.AutoTokenizer.from_pretrained(
                    "Qwen/Qwen2.5-7B-Instruct",
                    revison="bb46c15ee4bb56c5b63245ef50fd7637234d6f75",
                )
            elif "qwen2.5-coder" in self.model.lower():
                self.tokenizer = transformers.AutoTokenizer.from_pretrained(
                    "Qwen/Qwen2.5-Coder-7B-Instruct",
                    revison="7b148ce7a59a361780846419d31d271537addf81",
                )
            else:
                self.tokenizer = transformers.AutoTokenizer.from_pretrained(self.model)
        else:
            self.tokenizer = transformers.AutoTokenizer.from_pretrained(self.model)

    def token_num(self, text: Union[str, List[Dict[str, str]]]) -> int:
        """
        Return the number of tokens in the text.

        Args:
            text: The text to count the tokens of, or a list of messages.

        Returns:
            The number of tokens in the text.
        """
        if isinstance(self.tokenizer, tiktoken.Encoding):
            if not isinstance(text, str):
                num = openai_num_tokens_from_messages(text, self.model)
            else:
                model_inputs = self.tokenizer.encode(text)
                num = len(model_inputs)
            return num
        elif isinstance(self.tokenizer, transformers.PreTrainedTokenizerBase):
            if isinstance(text, list):
                text_final = self.tokenizer.apply_chat_template(
                    text, tokenize=False, add_generation_prompt=True
                )
            elif isinstance(text, str):
                text_final = text
            else:
                raise TypeError(
                    "Input text must be either a string or a list of dictionaries."
                )

            model_inputs = self.tokenizer.encode(text_final)  # type: ignore
            return len(model_inputs)
        else:
            raise Exception("Invalid tokenizer")

    def tokenize(
        self,
        text: str,
        pair: Optional[str] = None,
        add_special_tokens: bool = False,
        **kwargs,
    ) -> List[str]:
        """
        Converts a string into a sequence of tokens, replacing unknown tokens with the `unk_token`.

        Args:
            text (`str`):
                The sequence to be encoded.
            pair (`str`, *optional*):
                A second sequence to be encoded with the first.
            add_special_tokens (`bool`, *optional*, defaults to `False`):
                Whether or not to add the special tokens associated with the corresponding model.
            kwargs (additional keyword arguments, *optional*):
                Will be passed to the underlying model specific encode method. See details in
                [`~PreTrainedTokenizerBase.__call__`]

        Returns:
            `List[str]`: The list of tokens.
        """
        if isinstance(self.tokenizer, tiktoken.Encoding):
            raise Exception("Unsupported method")
        elif isinstance(self.tokenizer, transformers.PreTrainedTokenizerBase):
            return self.tokenizer.tokenize(
                text=text, pair=pair, add_special_tokens=add_special_tokens, **kwargs
            )
        else:
            raise Exception("Unknown tokenizer type.")

    def encode(
        self,
        text: Union[TextInput, PreTokenizedInput, EncodedInput],
        text_pair: Optional[Union[TextInput, PreTokenizedInput, EncodedInput]] = None,
        add_special_tokens: bool = True,
        padding: Union[bool, str, PaddingStrategy] = False,
        truncation: Optional[Union[bool, str, TruncationStrategy]] = None,
        max_length: Optional[int] = None,
        stride: int = 0,
        padding_side: Optional[bool] = None,
        return_tensors: Optional[Union[str, TensorType]] = None,
        **kwargs,
    ) -> List[int]:
        """
        Converts a string to a sequence of ids (integer), using the tokenizer and vocabulary.

        Same as doing `self.convert_tokens_to_ids(self.tokenize(text))`.

        Args:
            text (`str`, `List[str]` or `List[int]`):
                The first sequence to be encoded. This can be a string, a list of strings (tokenized string using the
                `tokenize` method) or a list of integers (tokenized string ids using the `convert_tokens_to_ids`
                method).
            text_pair (`str`, `List[str]` or `List[int]`, *optional*):
                Optional second sequence to be encoded. This can be a string, a list of strings (tokenized string using
                the `tokenize` method) or a list of integers (tokenized string ids using the `convert_tokens_to_ids`
                method).
        """
        if isinstance(self.tokenizer, tiktoken.Encoding):
            raise Exception("Unsupported method")
        elif isinstance(self.tokenizer, transformers.PreTrainedTokenizerBase):
            return self.tokenizer.encode(
                text=text,
                text_pair=text_pair,
                add_special_tokens=add_special_tokens,
                padding=padding,
                truncation=truncation if truncation is not None else False,
                max_length=max_length,
                stride=stride,
                padding_side=padding_side,
                return_tensors=return_tensors,
                **kwargs,
            )
        else:
            raise Exception("Unknown tokenizer type.")

    def __call__(
        self,
        text: Optional[
            TextInput | PreTokenizedInput | List[TextInput] | List[PreTokenizedInput]
        ] = None,
        text_pair: Optional[
            Union[
                TextInput, PreTokenizedInput, List[TextInput], List[PreTokenizedInput]
            ]
        ] = None,
        text_target: Optional[
            TextInput | PreTokenizedInput | List[TextInput] | List[PreTokenizedInput]
        ] = None,
        text_pair_target: Optional[
            Union[
                TextInput, PreTokenizedInput, List[TextInput], List[PreTokenizedInput]
            ]
        ] = None,
        add_special_tokens: bool = True,
        padding: Union[bool, str, PaddingStrategy] = False,
        truncation: Optional[Union[bool, str, TruncationStrategy]] = None,
        max_length: Optional[int] = None,
        stride: int = 0,
        is_split_into_words: bool = False,
        pad_to_multiple_of: Optional[int] = None,
        padding_side: Optional[bool] = None,
        return_tensors: Optional[Union[str, TensorType]] = None,
        return_token_type_ids: Optional[bool] = None,
        return_attention_mask: Optional[bool] = None,
        return_overflowing_tokens: bool = False,
        return_special_tokens_mask: bool = False,
        return_offsets_mapping: bool = False,
        return_length: bool = False,
        verbose: bool = True,
        **kwargs,
    ) -> BatchEncoding:
        """
        Main method to tokenize and prepare for the model one or several sequence(s) or one or several pair(s) of
        sequences.

        Args:
            text (`str`, `List[str]`, `List[List[str]]`, *optional*):
                The sequence or batch of sequences to be encoded. Each sequence can be a string or a list of strings
                (pretokenized string). If the sequences are provided as list of strings (pretokenized), you must set
                `is_split_into_words=True` (to lift the ambiguity with a batch of sequences).
            text_pair (`str`, `List[str]`, `List[List[str]]`, *optional*):
                The sequence or batch of sequences to be encoded. Each sequence can be a string or a list of strings
                (pretokenized string). If the sequences are provided as list of strings (pretokenized), you must set
                `is_split_into_words=True` (to lift the ambiguity with a batch of sequences).
            text_target (`str`, `List[str]`, `List[List[str]]`, *optional*):
                The sequence or batch of sequences to be encoded as target texts. Each sequence can be a string or a
                list of strings (pretokenized string). If the sequences are provided as list of strings (pretokenized),
                you must set `is_split_into_words=True` (to lift the ambiguity with a batch of sequences).
            text_pair_target (`str`, `List[str]`, `List[List[str]]`, *optional*):
                The sequence or batch of sequences to be encoded as target texts. Each sequence can be a string or a
                list of strings (pretokenized string). If the sequences are provided as list of strings (pretokenized),
                you must set `is_split_into_words=True` (to lift the ambiguity with a batch of sequences).
        """
        if isinstance(self.tokenizer, tiktoken.Encoding):
            raise Exception("Unsupported method")
        elif isinstance(self.tokenizer, transformers.PreTrainedTokenizerBase):
            return self.tokenizer.__call__(
                text=text,
                text_pair=text_pair,
                text_target=text_target,
                text_pair_target=text_pair_target,
                add_special_tokens=add_special_tokens,
                padding=padding,
                truncation=truncation if truncation is not None else False,
                max_length=max_length,
                stride=stride,
                is_split_into_words=is_split_into_words,
                pad_to_multiple_of=pad_to_multiple_of,
                padding_side=padding_side,
                return_tensors=return_tensors,
                return_token_type_ids=return_token_type_ids,
                return_attention_mask=return_attention_mask,
                return_overflowing_tokens=return_overflowing_tokens,
                return_special_tokens_mask=return_special_tokens_mask,
                return_offsets_mapping=return_offsets_mapping,
                return_length=return_length,
                verbose=verbose,
                **kwargs,
            )
        else:
            raise Exception("Unknown tokenizer type.")

    def apply_chat_template(
        self,
        conversation: Union[List[Dict[str, str]], List[List[Dict[str, str]]]],
        tools: Optional[List[Dict]] = None,
        documents: Optional[List[Dict[str, str]]] = None,
        chat_template: Optional[str] = None,
        add_generation_prompt: bool = False,
        continue_final_message: bool = False,
        tokenize: bool = True,
        padding: bool = False,
        truncation: bool = False,
        max_length: Optional[int] = None,
        return_tensors: Optional[Union[str, TensorType]] = None,
        return_dict: bool = False,
        return_assistant_tokens_mask: bool = False,
        tokenizer_kwargs: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Union[str, List[int], List[str], List[List[int]], BatchEncoding]:
        if isinstance(self.tokenizer, tiktoken.Encoding):
            raise Exception("Unsupported method")
        elif isinstance(self.tokenizer, transformers.PreTrainedTokenizerBase):
            return self.tokenizer.apply_chat_template(
                conversation=conversation,
                tools=tools,
                documents=documents,
                chat_template=chat_template,
                add_generation_prompt=add_generation_prompt,
                continue_final_message=continue_final_message,
                tokenize=tokenize,
                padding=padding,
                truncation=truncation,
                max_length=max_length,
                return_tensors=return_tensors,
                return_dict=return_dict,
                return_assistant_tokens_mask=return_assistant_tokens_mask,
                tokenizer_kwargs=tokenizer_kwargs,
                **kwargs,
            )
        else:
            raise Exception("Unknown tokenizer type.")
