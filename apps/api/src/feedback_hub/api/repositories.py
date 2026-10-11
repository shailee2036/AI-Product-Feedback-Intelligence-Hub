from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from feedback_hub.config import Settings, get_settings
from feedback_hub.github.client import (
    GitHubClient,
    GitHubError,
    GitHubRateLimitedError,
    RepositoryNotFoundError,
)
from feedback_hub.github.eligibility import EligibilityResult, evaluate_eligibility
from feedback_hub.github.refs import InvalidRepositoryReferenceError, parse_repository_reference

router = APIRouter(prefix="/v1/repositories", tags=["repositories"])


class EligibilityRequest(BaseModel):
    repository: str = Field(min_length=3, max_length=200, examples=["appwrite/appwrite"])


def get_github_client(request: Request) -> GitHubClient:
    client: GitHubClient = request.app.state.github
    return client


@router.post("/eligibility", response_model=EligibilityResult)
async def check_eligibility(
    body: EligibilityRequest,
    github: Annotated[GitHubClient, Depends(get_github_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> EligibilityResult:
    try:
        ref = parse_repository_reference(body.repository)
    except InvalidRepositoryReferenceError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    try:
        payload = await github.get_repository(ref)
    except RepositoryNotFoundError as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Repository not found or not public."
        ) from exc
    except GitHubRateLimitedError as exc:
        headers = {"Retry-After": "60"}
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "GitHub rate limit reached.", headers
        ) from exc
    except GitHubError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

    return evaluate_eligibility(payload, settings.allowed_licenses)
