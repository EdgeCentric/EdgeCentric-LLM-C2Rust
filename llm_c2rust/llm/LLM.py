from llm_c2rust.llm.api_inference import AsyncAPIInference


class Agent:

    def __init__(self, predicator: AsyncAPIInference) -> None:
        self.predicator = predicator

    def calculate_message_length(self, messages):
        total_length = sum(
            len(key) + len(value) for d in messages for key, value in d.items()
        )
        return total_length


class EdgeCentricAgent(Agent):
    predicator: AsyncAPIInference

    async def generate_rust(
        self,
        source: str,
        previous_result: str,
        signatures: str,
        max_tokens: int | None = None,
        temperature: float = 0.0,
    ):
        user_content = """I am translating a C project into Rust. Due to limited tokens, in each iteration I will only provide some of the code snippets—referred to as a 'context'. Since each snippet might have been translated before in different contexts, I am also including its previous translation results. Additionally, I will provide some already-translated function signatures for related functions as references.
When translating, please follow these guidelines:
- Only translate the code within the current context.
- Use the provided previous translation and signatures of related functions as references.
- Do not change parts of the previous translation that are unrelated to the current context unless absolutely necessary.
- If you modified parts of previous translation, please leave sufficient comments around the changes to explain your modifications.
- Your translation should be complete. Do not omit parts of the translation when they remain unchanged.
Your goal is to ensure the translation remains consistent across contexts while accurately reflecting the current context.
"""
        user_content = "Source Code \n```\n" + source + "\n```\n"

        if previous_result:
            user_content += "Previous Translation:\n```rust\n"
            user_content += previous_result
            user_content += "```\n"
        else:
            user_content += "No previous translation available.\n"

        if signatures:
            user_content += "Related Function Signatures:\n```rust\n"
            user_content += signatures
            user_content += "```\n"
        else:
            user_content += "No related function signatures available.\n"

        messages = [
            {
                "role": "system",
                "content": "You are an expert programming assistant familiar with C/C++ and Rust, helping to translate a C/C++ project into Rust.",
            },
            {"role": "user", "content": user_content},
        ]
        llm_res = await self.predicator.chat(
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return llm_res or ""

    async def resolve_conflicts(
        self,
        err_msg: str,
        rust_code: str,
        max_tokens: int | None = None,
        temperature: float = 0.0,
    ):

        user_content = (
            "I have a Rust code snippet that has compilation errors and needs to be fixed. "
            "Please provide only one markdown code block that contains the single best fix you recommend. "
            "The code inside the block should be a complete and final version of the snippet, not a partial fix. "
            "Do not include any extra code outside of the snippet, even if there are external references in the code. "
            "\n"
        )

        user_content += "The error message is:\n```\n" + err_msg + "\n```\n"
        user_content += "The Rust code is:\n```rust\n" + rust_code + "\n```\n"

        messages = [
            {
                "role": "system",
                "content": "You are an expert programming assistant familiar with Rust, helping to fix a buggy Rust project.",
            },
            {"role": "user", "content": user_content},
        ]
        llm_res = await self.predicator.chat(
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return llm_res or ""

    async def fix_grammar(
        self,
        rust_code: str,
        err_msg: str,
        max_tokens: int | None = None,
        temperature: float = 0.0,
    ):
        user_content = (
            "I have a Rust code snippet that has some syntax errors and needs to be corrected. "
            "Please provide only one markdown code block that contains the single best correction you recommend. "
            "The code inside the block should be a complete and final version of the snippet, not a partial fix. "
            "Focus strictly on syntax-related issues. Do not introduce any improvements, optimizations, or refactorings."
            "\n"
        )
        user_content += "The error message is:\n```\n" + err_msg + "\n```\n"
        user_content += "The Rust code is:\n```rust\n" + rust_code + "\n```\n"
        messages = [
            {
                "role": "system",
                "content": "You are an expert programming assistant familiar with Rust.",
            },
            {"role": "user", "content": user_content},
        ]

        llm_res = await self.predicator.chat(
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return llm_res or ""


class NodeCentricAgent(Agent):

    async def generate_rust(
        self,
        source: str,
        dependency_summary: str,
        max_tokens: int | None = None,
        temperature: float = 0.0,
    ):
        user_content = """I am translating some code snippets of a C project into Rust. I will provide summary of translated dependencies as references. """
        user_content = "Source Code \n```\n" + source + "\n```\n"

        if dependency_summary:
            user_content += "Summary of dependencies:\n```rust\n"
            user_content += dependency_summary
            user_content += "```\n"
        else:
            user_content += "No summary of dependencies available.\n"

        messages = [
            {
                "role": "system",
                "content": "You are an expert programming assistant familiar with C/C++ and Rust, helping to translate a C/C++ project into Rust.",
            },
            {"role": "user", "content": user_content},
        ]

        llm_res = await self.predicator.chat(
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return llm_res or ""

    async def resolve_conflicts(
        self,
        err_msg: str,
        rust_code: str,
        max_tokens: int | None = None,
        temperature: float = 0.0,
    ):

        user_content = (
            "I have some Rust code snippets that have compilation errors. "
            "Please provide only one markdown code block that contains the single best fix you recommend. "
            "The code inside the block should be a complete and final version of the snippet, not a partial fix. "
            "Do not omit parts of the code even when they are correct. "
        )

        user_content += "The error message is:\n```\n" + err_msg + "\n```\n"
        user_content += "The Rust code is:\n```rust\n" + rust_code + "\n```\n"

        messages = [
            {
                "role": "system",
                "content": "You are an expert programming assistant familiar with Rust, helping to fix a buggy Rust project.",
            },
            {"role": "user", "content": user_content},
        ]

        llm_res = await self.predicator.chat(
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return llm_res or ""
