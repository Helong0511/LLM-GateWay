"""LiteLLM 执行面注册：把管理后台的「上架/下架/换凭证」同步给 LiteLLM。

背景：`/v1` 转发全部打给 LiteLLM，而 provider / 凭证 / 模型目录只存在自家库。
两边没有同步通道时，后台「上架成功」在真实调用上等于 400 model not found。
这里通过 LiteLLM Admin API（`/model/new`、`/model/delete`、`/model/info`）补齐。

设计约束：
- **不阻断主流程**：LiteLLM 抖动不应该让上架事务失败，失败原因写入
  `model_deployments.registry_error`，由 worker 定时对账补偿；
- **幂等**：`model_info.id` 固定用 deployment.id，重复 `POST /model/new` 即覆盖；
- **凭证不落日志**：只在请求体里出现，`details` 一律不带 key。
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import structlog

from app.core.config import Settings

logger = structlog.get_logger("forgeapi.providers.registry")

# provider.kind → LiteLLM 的 provider 前缀。cloud/compatible/self_hosted 都按
# OpenAI 兼容协议处理；anthropic 走原生 messages 协议。
_KIND_PREFIX = {
    "openai": "openai",
    "anthropic": "anthropic",
    "ollama": "ollama",
    "cloud": "openai",
    "compatible": "openai",
    "self_hosted": "openai",
}


def litellm_model_ref(kind: str, upstream_name: str) -> str:
    return f"{_KIND_PREFIX.get(kind, 'openai')}/{upstream_name}"


class LiteLLMRegistry:
    """LiteLLM Admin API 的最小封装。"""

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.settings = settings
        self.transport = transport
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.settings.litellm_sync_enabled and self.settings.litellm_base_url)

    def _headers(self) -> dict[str, str]:
        return {"authorization": f"Bearer {self.settings.litellm_master_key}"}

    def _url(self, path: str) -> str:
        return self.settings.litellm_base_url.rstrip("/") + path

    async def upsert(
        self,
        *,
        deployment_id: str,
        model_name: str,
        kind: str,
        upstream_name: str,
        api_base: str,
        api_key: str,
    ) -> None:
        """注册或覆盖一个 deployment。同名 model_name 的多条记录即负载均衡组。"""
        if not self.configured:
            return
        payload: dict[str, Any] = {
            "model_name": model_name,
            "litellm_params": {
                "model": litellm_model_ref(kind, upstream_name),
                "api_base": api_base,
                "api_key": api_key,
            },
            # id 决定幂等性与删除目标；LiteLLM 用它做 model_info 主键。
            "model_info": {"id": deployment_id, "base_model": upstream_name},
        }
        await self._request("POST", "/model/new", payload)

    async def remove(self, deployment_id: str) -> None:
        if not self.configured:
            return
        await self._request("POST", "/model/delete", {"id": deployment_id})

    async def list_ids(self) -> set[str]:
        """返回 LiteLLM 侧已知的 deployment id 集合，供对账使用。"""
        if not self.configured:
            return set()
        body = await self._request("GET", "/model/info")
        data = body.get("data")
        ids: set[str] = set()
        if isinstance(data, list):
            for item in data:
                if not isinstance(item, dict):
                    continue
                info = item.get("model_info")
                if isinstance(info, dict) and isinstance(info.get("id"), str):
                    ids.add(info["id"])
        return ids

    async def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            if self.transport is not None:
                async with httpx.AsyncClient(transport=self.transport, timeout=self.timeout) as client:
                    response = await client.request(
                        method, self._url(path), headers=self._headers(), json=payload
                    )
            else:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.request(
                        method, self._url(path), headers=self._headers(), json=payload
                    )
        except httpx.HTTPError as exc:
            logger.warning("litellm_unreachable", path=path, error_type=type(exc).__name__)
            raise RegistryError("LiteLLM 不可达，注册将在对账任务中重试") from exc
        if response.status_code >= 400:
            detail = response.text[:200]
            logger.warning("litellm_registry_error", path=path, status=response.status_code)
            raise RegistryError(f"LiteLLM 返回 {response.status_code}: {detail}")
        if not response.content:
            return {}
        try:
            body = response.json()
        except json.JSONDecodeError as exc:
            raise RegistryError("LiteLLM 返回非 JSON 响应") from exc
        return body if isinstance(body, dict) else {}


class RegistryError(RuntimeError):
    """注册失败。调用方负责记录并留给对账补偿，不向上抛给用户。"""
