"""数据提供器的 Parquet 缓存基础设施。"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from typing import TYPE_CHECKING, Any, Callable, Optional

import pandas as pd

if TYPE_CHECKING:
    from .config import BaseProviderConfig


class DataProviderBase:
    """提供稳定的 Parquet 缓存和 DataFrame 基础校验。"""

    provider_name = "base"
    cache_version = "1"
    DEFAULT_CACHE_DIR = "data/cache"

    def __init__(
        self,
        cache_dir: Optional[str] = None,
        config: Optional["BaseProviderConfig"] = None,
    ) -> None:
        self.config = config
        configured_cache = config.cache_dir if config and config.cache_dir else None
        self.cache_dir = os.path.abspath(cache_dir or configured_cache or self.DEFAULT_CACHE_DIR)
        os.makedirs(self.cache_dir, exist_ok=True)

    def _generate_cache_key(self, dataset: str, **params: Any) -> str:
        payload = {
            "cache_version": self.cache_version,
            "provider": self.provider_name,
            "dataset": dataset,
            "params": params,
        }
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)

    def _cache_path(self, key: str) -> str:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        try:
            payload = json.loads(key)
        except (TypeError, json.JSONDecodeError):
            payload = {}
        params = payload.get("params", {}) if isinstance(payload, dict) else {}
        dataset = self._safe_cache_component(payload.get("dataset"), "dataset")
        start_date = self._safe_cache_component(params.get("start_date"), "no-start")
        end_date = self._safe_cache_component(params.get("end_date"), "no-end")
        filename = f"{dataset}_{start_date}_{end_date}_{digest[:20]}.parquet"
        return os.path.join(self.cache_dir, filename)

    def _legacy_cache_path(self, key: str) -> str:
        """兼容读取旧版仅使用完整哈希命名的缓存。"""
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return os.path.join(self.cache_dir, f"{digest}.parquet")

    @staticmethod
    def _safe_cache_component(value: Any, fallback: str) -> str:
        if value is None or str(value).strip() == "":
            return fallback
        cleaned = re.sub(r"[^0-9A-Za-z._-]+", "-", str(value).strip())
        return cleaned.strip("-._") or fallback

    def _load_cached(self, key: str) -> Optional[pd.DataFrame]:
        for path in (self._cache_path(key), self._legacy_cache_path(key)):
            if os.path.exists(path):
                return pd.read_parquet(path)
        return None

    def _cache_result(self, key: str, data: pd.DataFrame) -> None:
        final_path = self._cache_path(key)
        descriptor, temporary_path = tempfile.mkstemp(dir=self.cache_dir, suffix=".parquet")
        os.close(descriptor)
        try:
            data.to_parquet(temporary_path, index=False)
            os.replace(temporary_path, final_path)
        finally:
            if os.path.exists(temporary_path):
                os.unlink(temporary_path)

    def _fetch(
        self,
        *,
        key: str,
        loader: Callable[[], pd.DataFrame],
        force_refresh: bool = False,
    ) -> pd.DataFrame:
        if not force_refresh:
            cached = self._load_cached(key)
            if cached is not None:
                return cached

        data = loader()
        if not isinstance(data, pd.DataFrame):
            raise TypeError("provider must return a pandas DataFrame")
        data = data.copy().reset_index(drop=True)
        data.columns = [str(column) for column in data.columns]
        self._cache_result(key, data)
        return data
