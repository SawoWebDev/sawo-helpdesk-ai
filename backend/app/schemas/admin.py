from pydantic import BaseModel, Field


class DangerousActionConfirm(BaseModel):
    """Body required by any endpoint that destroys data in bulk. The UI
    collects a typed confirmation phrase plus the signed-in admin's own
    credentials again, so a stray click (or a session left open on someone
    else's screen) can't wipe data silently — see
    app.core.deps.require_dangerous_action_confirmation."""

    confirm_text: str = Field(..., description='Must exactly match "DELETE THIS".')
    username: str
    password: str
