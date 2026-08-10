from typing import Annotated

from fastapi import Depends, Request

from app.storage.base import StorageProvider


def get_document_storage(request: Request) -> StorageProvider:
    return request.app.state.document_storage


DocumentStorage = Annotated[StorageProvider, Depends(get_document_storage)]
