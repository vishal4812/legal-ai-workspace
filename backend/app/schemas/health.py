from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    service: str


class ApiRootResponse(BaseModel):
    name: str
    version: str
