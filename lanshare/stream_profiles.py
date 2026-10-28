from dataclasses import dataclass


@dataclass(frozen=True)
class StreamProfile:
    label: str
    max_width: int  # 0 = full native width
    jpeg_quality: int
    fps_max: int
    fps_min: int
    jpeg_subsample: int | None  # None = OpenCV default 4:2:0 (fastest)


PROFILES: dict[str, StreamProfile] = {
    "quality": StreamProfile("清晰（高画质）", 0, 94, 32, 10, 0x111111),
    "balanced": StreamProfile("平衡（推荐）", 2560, 90, 40, 12, 0x221111),
    "speed": StreamProfile("流畅（低延迟）", 1680, 84, 48, 18, None),
}

DEFAULT_PROFILE = "balanced"


def get_profile(key: str) -> StreamProfile:
    return PROFILES.get(key, PROFILES[DEFAULT_PROFILE])
