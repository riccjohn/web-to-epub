from dataclasses import dataclass, field


@dataclass(frozen=True)
class ImageRef:
    src: str
    alt: str = ""
    caption: str | None = None
    is_remote: bool = True


@dataclass(frozen=True)
class Chapter:
    title: str = ""
    body: str = ""
    images: list[ImageRef] = field(default_factory=list)
