from typing import TypedDict, List, Optional

class VKPostData(TypedDict):
    text: str
    images: List[str]

class TwitterPostData(TypedDict):
    text: str
    images: List[str]
    videos: List[str]

class DownloadResult(TypedDict):
    success: bool
    file_path: Optional[str]
    error: Optional[str]