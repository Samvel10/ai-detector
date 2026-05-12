from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from redis import Redis


STREAM_TYPES = ("timeline", "tracking", "graph", "semantic", "prediction", "system")


@dataclass(frozen=True)
class StreamEnvelope:
    sequence_id: int
    video_id: str
    stream_type: str
    version_hash: str
    payload: dict[str, Any]

    def as_stream_fields(self) -> dict[str, str]:
        return {
            "sequence_id": str(self.sequence_id),
            "video_id": self.video_id,
            "stream_type": self.stream_type,
            "version_hash": self.version_hash,
            "payload": json.dumps(self.payload, ensure_ascii=True),
        }


class RealtimeStreamPublisher:
    def __init__(self, redis_client: Redis, namespace: str = "stream") -> None:
        self.redis = redis_client
        self.namespace = namespace

    def _stream_key(self, video_id: str, stream_type: str) -> str:
        return f"{self.namespace}:video:{video_id}:{stream_type}"

    def _sequence_key(self, video_id: str, stream_type: str) -> str:
        return f"{self.namespace}:seq:{video_id}:{stream_type}"

    def _version_key(self, video_id: str, stream_type: str) -> str:
        return f"{self.namespace}:version:{video_id}:{stream_type}"

    def next_sequence(self, video_id: str, stream_type: str) -> int:
        return int(self.redis.incr(self._sequence_key(video_id, stream_type)))

    def publish(self, video_id: str, stream_type: str, version_hash: str, payload: dict[str, Any]) -> str | None:
        if stream_type not in STREAM_TYPES:
            raise ValueError(f"Unsupported stream type: {stream_type}")
        version_key = self._version_key(video_id, stream_type)
        existing = self.redis.get(version_key)
        if existing == version_hash:
            return None

        sequence_id = self.next_sequence(video_id, stream_type)
        envelope = StreamEnvelope(
            sequence_id=sequence_id,
            video_id=video_id,
            stream_type=stream_type,
            version_hash=version_hash,
            payload=payload,
        )
        stream_id = self.redis.xadd(self._stream_key(video_id, stream_type), envelope.as_stream_fields(), maxlen=5000)
        self.redis.set(version_key, version_hash)
        return stream_id
