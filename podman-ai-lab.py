#*********************************************************************
# Copyright (C) 2025 Red Hat, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0
#**********************************************************************/

import json
from typing import Any, AsyncGenerator, AsyncIterator, Dict, List, Optional, Union

import httpx

from llama_stack.apis.common.content_types import (
    ImageContentItem,
    InterleavedContent,
    InterleavedContentItem,
    TextContentItem,
)
from llama_stack.apis.inference import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    CompletionRequest,
    EmbeddingsResponse,
    EmbeddingTaskType,
    Inference,
    LogProbConfig,
    Message,
    OpenAIChatCompletion,
    OpenAIChatCompletionChunk,
    OpenAIEmbeddingsResponse,
    OpenAIMessageParam,
    OpenAIResponseFormatParam,
    ResponseFormat,
    SamplingParams,
    TextTruncation,
    ToolChoice,
    ToolConfig,
    ToolDefinition,
    ToolPromptFormat,
)
from llama_stack.apis.inference.inference import (
    OpenAICompletion,
)

from llama_stack.apis.models import Model, Models
from llama_stack.log import get_logger
from llama_stack.providers.datatypes import ModelsProtocolPrivate
from llama_stack.providers.utils.inference.openai_compat import (
    OpenAICompatCompletionChoice,
    OpenAICompatCompletionResponse,
    get_sampling_options,
    process_chat_completion_response,
    process_chat_completion_stream_response,
    process_completion_response,
    process_completion_stream_response,
)
from llama_stack.providers.utils.inference.prompt_adapter import (
    completion_request_to_prompt,
    convert_image_content_to_url,
    request_has_media,
)

logger = get_logger(name=__name__, category="inference")


class PodmanAILabInferenceAdapter(Inference, ModelsProtocolPrivate):
    def __init__(self, url: str) -> None:
        self.url = url.rstrip("/")

    @property
    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self.url, timeout=120.0)

    async def initialize(self) -> None:
        logger.info(f"checking connectivity to backend at `{self.url}`...")
        try:
            async with self.client as c:
                r = await c.get("/v1/models")
                r.raise_for_status()
                logger.info(f"connected successfully, models: {[m.get('id') for m in r.json().get('data', [])]}")
        except Exception as e:
            raise RuntimeError(f"Backend server at {self.url} is not reachable: {e}") from e

    async def shutdown(self) -> None:
        pass

    async def unregister_model(self, model_id: str) -> None:
        pass

    async def completion(
        self,
        model_id: str,
        content: InterleavedContent,
        sampling_params: Optional[SamplingParams] = None,
        response_format: Optional[ResponseFormat] = None,
        stream: Optional[bool] = False,
        logprobs: Optional[LogProbConfig] = None,
    ) -> AsyncGenerator:
        if sampling_params is None:
            sampling_params = SamplingParams()
        model = await self.model_store.get_model(model_id)
        request = CompletionRequest(
            model=model.provider_resource_id,
            content=content,
            sampling_params=sampling_params,
            response_format=response_format,
            stream=stream,
            logprobs=logprobs,
        )
        if stream:
            return self._stream_completion(request)
        else:
            return await self._nonstream_completion(request)

    async def _stream_completion(self, request: CompletionRequest) -> AsyncGenerator:
        params = await self._build_completion_params(request)
        params["stream"] = True

        async with self.client as c:
            async with c.stream("POST", "/v1/completions", json=params) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data.strip() == "[DONE]":
                        break
                    chunk = json.loads(data)
                    text = chunk.get("choices", [{}])[0].get("text", "")
                    finish_reason = chunk.get("choices", [{}])[0].get("finish_reason")
                    choice = OpenAICompatCompletionChoice(
                        finish_reason=finish_reason,
                        text=text,
                    )
                    yield OpenAICompatCompletionResponse(choices=[choice])

    async def _nonstream_completion(self, request: CompletionRequest) -> AsyncGenerator:
        params = await self._build_completion_params(request)
        params["stream"] = False

        async with self.client as c:
            r = await c.post("/v1/completions", json=params)
            r.raise_for_status()
            data = r.json()

        choice_data = data["choices"][0]
        choice = OpenAICompatCompletionChoice(
            finish_reason=choice_data.get("finish_reason"),
            text=choice_data.get("text", ""),
        )
        response = OpenAICompatCompletionResponse(choices=[choice])
        return process_completion_response(response)

    async def chat_completion(
        self,
        model_id: str,
        messages: List[Message],
        sampling_params: Optional[SamplingParams] = None,
        response_format: Optional[ResponseFormat] = None,
        tools: Optional[List[ToolDefinition]] = None,
        tool_choice: Optional[ToolChoice] = ToolChoice.auto,
        tool_prompt_format: Optional[ToolPromptFormat] = None,
        stream: Optional[bool] = False,
        logprobs: Optional[LogProbConfig] = None,
        tool_config: Optional[ToolConfig] = None,
    ) -> AsyncGenerator:
        if sampling_params is None:
            sampling_params = SamplingParams()
        request = ChatCompletionRequest(
            model=model_id,
            messages=messages,
            sampling_params=sampling_params,
            tools=tools or [],
            stream=stream,
            logprobs=logprobs,
            response_format=response_format,
            tool_config=tool_config,
        )
        if stream:
            return self._stream_chat_completion(request)
        else:
            return await self._nonstream_chat_completion(request)

    async def _build_completion_params(self, request) -> dict:
        sampling_options = get_sampling_options(request.sampling_params)
        if sampling_options.get("max_tokens") is not None:
            sampling_options.pop("max_tokens", None)

        input_dict = {}
        if isinstance(request, ChatCompletionRequest):
            input_dict["messages"] = []
            for m in request.messages:
                if isinstance(m.content, list):
                    for c in m.content:
                        if isinstance(c, TextContentItem):
                            input_dict["messages"].append({"role": m.role, "content": c.text})
                        else:
                            input_dict["messages"].append({"role": m.role, "content": str(c)})
                else:
                    text = m.content.text if isinstance(m.content, TextContentItem) else str(m.content)
                    input_dict["messages"].append({"role": m.role, "content": text})
        else:
            input_dict["prompt"] = await completion_request_to_prompt(request)

        params = {
            "model": request.model,
            **input_dict,
            **sampling_options,
            "stream": request.stream,
        }
        return params

    async def _nonstream_chat_completion(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        params = await self._build_completion_params(request)

        async with self.client as c:
            r = await c.post("/v1/chat/completions", json=params)
            r.raise_for_status()
            data = r.json()

        choice_data = data["choices"][0]
        content = choice_data.get("message", {}).get("content", "")
        choice = OpenAICompatCompletionChoice(
            finish_reason=choice_data.get("finish_reason"),
            text=content,
        )
        response = OpenAICompatCompletionResponse(choices=[choice])
        return process_chat_completion_response(response, request)

    async def _stream_chat_completion(self, request: ChatCompletionRequest) -> AsyncGenerator:
        params = await self._build_completion_params(request)

        async with self.client as c:
            async with c.stream("POST", "/v1/chat/completions", json=params) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data.strip() == "[DONE]":
                        break
                    chunk = json.loads(data)
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content", "")
                    finish_reason = chunk.get("choices", [{}])[0].get("finish_reason")
                    choice = OpenAICompatCompletionChoice(
                        finish_reason=finish_reason,
                        text=content,
                    )
                    yield OpenAICompatCompletionResponse(choices=[choice])

    async def embeddings(
        self,
        model_id: str,
        contents: List[str] | List[InterleavedContentItem],
        text_truncation: Optional[TextTruncation] = TextTruncation.none,
        output_dimension: Optional[int] = None,
        task_type: Optional[EmbeddingTaskType] = None,
    ) -> EmbeddingsResponse:
        raise NotImplementedError("embeddings endpoint is not implemented")

    async def register_model(self, model: Model) -> Model:
        return model

    async def openai_chat_completion(
        self,
        model: str,
        messages: List[OpenAIMessageParam],
        frequency_penalty: Optional[float] = None,
        function_call: Optional[Union[str, Dict[str, Any]]] = None,
        functions: Optional[List[Dict[str, Any]]] = None,
        logit_bias: Optional[Dict[str, float]] = None,
        logprobs: Optional[bool] = None,
        max_completion_tokens: Optional[int] = None,
        max_tokens: Optional[int] = None,
        n: Optional[int] = None,
        parallel_tool_calls: Optional[bool] = None,
        presence_penalty: Optional[float] = None,
        response_format: Optional[OpenAIResponseFormatParam] = None,
        seed: Optional[int] = None,
        stop: Optional[Union[str, List[str]]] = None,
        stream: Optional[bool] = None,
        stream_options: Optional[Dict[str, Any]] = None,
        temperature: Optional[float] = None,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        top_logprobs: Optional[int] = None,
        top_p: Optional[float] = None,
        user: Optional[str] = None,
    ) -> Union[OpenAIChatCompletion, AsyncIterator[OpenAIChatCompletionChunk]]:
        serialized_messages = []
        for m in messages:
            if hasattr(m, 'model_dump'):
                serialized_messages.append(m.model_dump(exclude_none=True))
            elif hasattr(m, 'dict'):
                serialized_messages.append(m.dict(exclude_none=True))
            else:
                serialized_messages.append(m)

        params = {
            "model": model,
            "messages": serialized_messages,
            "stream": stream or False,
        }
        if response_format is not None:
            if hasattr(response_format, 'model_dump'):
                params["response_format"] = response_format.model_dump(exclude_none=True)
            elif hasattr(response_format, 'dict'):
                params["response_format"] = response_format.dict(exclude_none=True)
            else:
                params["response_format"] = response_format
        if frequency_penalty is not None: params["frequency_penalty"] = frequency_penalty
        if max_completion_tokens is not None: params["max_completion_tokens"] = max_completion_tokens
        if max_tokens is not None: params["max_tokens"] = max_tokens
        if n is not None: params["n"] = n
        if presence_penalty is not None: params["presence_penalty"] = presence_penalty
        if seed is not None: params["seed"] = seed
        if stop is not None: params["stop"] = stop
        if temperature is not None: params["temperature"] = temperature
        if top_p is not None: params["top_p"] = top_p
        if tools is not None:
            if isinstance(tools, list):
                params["tools"] = [t.model_dump(exclude_none=True) if hasattr(t, 'model_dump') else t for t in tools]
            else:
                params["tools"] = tools
        if tool_choice is not None: params["tool_choice"] = tool_choice
        if logprobs is not None: params["logprobs"] = logprobs
        if top_logprobs is not None: params["top_logprobs"] = top_logprobs
        if logit_bias is not None: params["logit_bias"] = logit_bias
        if stream_options is not None: params["stream_options"] = stream_options

        if stream:
            return self._openai_stream_chat_completion(params)

        async with self.client as c:
            r = await c.post("/v1/chat/completions", json=params)
            r.raise_for_status()
            data = r.json()

        return OpenAIChatCompletion(**data)

    async def _openai_stream_chat_completion(self, params: dict) -> AsyncGenerator:
        async with self.client as c:
            async with c.stream("POST", "/v1/chat/completions", json=params) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data.strip() == "[DONE]":
                        break
                    chunk = json.loads(data)
                    yield OpenAIChatCompletionChunk(**chunk)

    async def openai_embeddings(
        self,
        model: str,
        input: str | list[str],
        encoding_format: str | None = "float",
        dimensions: int | None = None,
        user: str | None = None,
    ) -> OpenAIEmbeddingsResponse:
        raise NotImplementedError()

    async def openai_completion(
        self,
        model: str,
        prompt: str | list[str] | list[int] | list[list[int]],
        best_of: int | None = None,
        echo: bool | None = None,
        frequency_penalty: float | None = None,
        logit_bias: dict[str, float] | None = None,
        logprobs: int | None = None,
        max_tokens: int | None = None,
        n: int | None = None,
        presence_penalty: float | None = None,
        seed: int | None = None,
        stop: str | list[str] | None = None,
        stream: bool | None = None,
        stream_options: dict[str, Any] | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        user: str | None = None,
        guided_choice: list[str] | None = None,
        prompt_logprobs: int | None = None,
        suffix: str | None = None,
    ) -> OpenAICompletion:
        raise NotImplementedError()
