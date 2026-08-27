from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from services import alexa_voice_service, agent_permission_service


router = APIRouter(prefix="/api/alexa", tags=["alexa"])


class AlexaRelayRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=255)
    request_id: str = Field(min_length=1, max_length=255)
    text: str = Field(min_length=1, max_length=4000)


@router.post("/relay")
async def relay(
    request: Request,
    x_vera_timestamp: str = Header(default=""),
    x_vera_signature: str = Header(default=""),
):
    body = await request.body()
    try:
        alexa_voice_service.authenticate(
            timestamp=x_vera_timestamp,
            signature=x_vera_signature,
            body=body,
        )
        payload = AlexaRelayRequest.model_validate_json(body)
        return alexa_voice_service.respond(user_id="owner", **payload.model_dump())
    except alexa_voice_service.AlexaRelayAuthenticationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except agent_permission_service.AgentPermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail="Alexa voice access is disabled.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid Alexa relay request.") from exc
