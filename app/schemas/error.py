from pydantic import BaseModel


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict | None = None
    request_id: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail

    model_config = {
        "json_schema_extra": {
            "example": {
                "error": {
                    "code": "COLLECTION_NOT_FOUND",
                    "message": "Collection dd8aa5b5-7b2a-4e1c-9f0d-1a2b3c4d5e6f does not exist",
                    "request_id": "8f4d2a1c-9b7e-4f6d-5a8c-2b1e4f7d9c3a",
                }
            }
        }
    }


# Reusable OpenAPI `responses=` dict. Attach to any route that accepts a
# Bearer-authenticated request and routes through a collection_id path param.
COMMON_ERROR_RESPONSES = {
    400: {"model": ErrorResponse, "description": "Invalid request body"},
    401: {"model": ErrorResponse, "description": "Missing or invalid API key"},
    403: {"model": ErrorResponse, "description": "API key lacks the required scope"},
    404: {"model": ErrorResponse, "description": "Collection or resource not found"},
    422: {"model": ErrorResponse, "description": "Request failed schema validation"},
    500: {"model": ErrorResponse, "description": "Internal server error"},
}
