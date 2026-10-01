"""What went wrong with a model call, in categories a person can act on.

Model calls fail for very different reasons — a rejected or empty-wallet provider key, a model
name the gateway doesn't know, an unreachable gateway, a conversation longer than the context
window — and each needs a different fix by a different person. Collapsing them all into "the
assistant ran into a problem" leaves nobody able to fix it, so every model failure is classified
here once and both the user-facing text and the server log use the category.

Classification is duck-typed (status code, exception class name, message text) because errors
arrive from several SDKs (OpenAI-compatible gateway, Anthropic, Google) and from LiteLLM, which
re-wraps upstream errors in its own text. Raw provider text never reaches the user: it can
contain account ids or fragments of the request.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ModelErrorKind(StrEnum):
    auth = "auth"  # key missing, invalid or revoked
    billing = "billing"  # key valid but out of credit / billing not set up
    forbidden = "forbidden"  # key has no access to this model
    model_not_found = "model_not_found"
    context_too_long = "context_too_long"
    content_blocked = "content_blocked"
    rate_limited = "rate_limited"
    timeout = "timeout"
    unreachable = "unreachable"  # gateway / provider could not be reached
    provider_error = "provider_error"  # provider answered with some other error
    internal = "internal"  # not a provider error: a bug on our side


@dataclass(frozen=True)
class ModelError:
    kind: ModelErrorKind
    status: int | None
    exc_type: str

    @property
    def is_provider(self) -> bool:
        return self.kind is not ModelErrorKind.internal


def _status(exc: BaseException) -> int | None:
    status = getattr(exc, "status_code", None) or getattr(
        getattr(exc, "response", None), "status_code", None
    )
    return status if isinstance(status, int) else None


_PROVIDER_MODULES = {
    "openai",
    "anthropic",
    "httpx",
    "httpx2",
    "httpcore",
    "litellm",
    "google",
    "langchain_google_genai",
}


def _looks_like_provider_error(exc: BaseException, name: str) -> bool:
    module = type(exc).__module__ or ""
    return (
        _status(exc) is not None
        or module.split(".")[0] in _PROVIDER_MODULES
        or name.endswith(("apierror", "apiconnectionerror", "apitimeouterror"))
    )


def classify(exc: BaseException) -> ModelError:
    status = _status(exc)
    name = type(exc).__name__.lower()
    text = str(exc).lower()

    def kind() -> ModelErrorKind:
        if isinstance(exc, TimeoutError):
            return ModelErrorKind.timeout
        # A database or programming error that merely mentions "connection" is ours, not the
        # provider's: only errors raised by a model SDK / HTTP client are classified further.
        if not _looks_like_provider_error(exc, name):
            return ModelErrorKind.internal
        # Order matters: LiteLLM reports upstream billing/context problems as 400s.
        if (
            status == 402
            or "credit balance" in text
            or "insufficient credits" in text
            or "insufficient_quota" in text
            or "billing" in text
            or "payment required" in text
        ):
            return ModelErrorKind.billing
        if (
            "context_length" in text
            or "context length" in text
            or "context window" in text
            or "prompt is too long" in text
            or "maximum context" in text
            or "too many tokens" in text
        ):
            return ModelErrorKind.context_too_long
        if status == 401 or "authentication" in name or "api key" in text or "x-api-key" in text:
            return ModelErrorKind.auth
        if "unauthorized" in text or "invalid_api_key" in text:
            return ModelErrorKind.auth
        if status == 403 or "permissiondenied" in name:
            return ModelErrorKind.forbidden
        if (
            status == 404
            or "notfound" in name
            or "model_not_found" in text
            or "does not exist" in text
            or "invalid model name" in text
        ):
            return ModelErrorKind.model_not_found
        if "content_filter" in text or "content policy" in text or "safety setting" in text:
            return ModelErrorKind.content_blocked
        if (
            status == 429
            or "ratelimit" in name
            or "rate limit" in text
            or "resource_exhausted" in text
            or "overloaded" in text
        ):
            return ModelErrorKind.rate_limited
        if "timeout" in name or "timed out" in text:
            return ModelErrorKind.timeout
        if (
            "connect" in name
            or "connection" in text
            or "name or service not known" in text
            or "nodename nor servname" in text
            or status in (502, 503, 504)
        ):
            return ModelErrorKind.unreachable
        return ModelErrorKind.provider_error

    return ModelError(kind=kind(), status=status, exc_type=type(exc).__name__)


_ADMIN = (
    "An admin needs to fix the AI provider settings; meanwhile you can add your own model "
    "under Settings → AI."
)

WORKSPACE_MESSAGES: dict[ModelErrorKind, str] = {
    ModelErrorKind.auth: "The AI provider rejected this server's API key. " + _ADMIN,
    ModelErrorKind.billing: "The AI provider account for this server is out of credit. " + _ADMIN,
    ModelErrorKind.forbidden: "This server's AI key doesn't have access to the selected model. "
    "Pick another model, or ask an admin to check the AI provider settings.",
    ModelErrorKind.model_not_found: "The selected model isn't available on this server. "
    "Pick another model, or ask an admin to check the AI gateway's model list.",
    ModelErrorKind.context_too_long: "This conversation is too long for the model. "
    "Start a new conversation, or shorten your message.",
    ModelErrorKind.content_blocked: "The AI provider declined to answer this request.",
    ModelErrorKind.rate_limited: "The AI provider is busy right now. Wait a minute and retry.",
    ModelErrorKind.timeout: "The AI service took too long to answer. Please try again.",
    ModelErrorKind.unreachable: "Notely couldn't reach its AI service. Try again in a minute; "
    "if it keeps happening, an admin should check that the AI gateway is running.",
    ModelErrorKind.provider_error: "The AI provider returned an error. Please try again, "
    "or pick a different model.",
    ModelErrorKind.internal: "The assistant ran into a problem. Please try again.",
}

OWN_KEY_MESSAGES: dict[ModelErrorKind, str] = {
    ModelErrorKind.auth: "The API key was rejected. Check the key and the provider.",
    ModelErrorKind.billing: "The provider says this key has no credit for that model.",
    ModelErrorKind.forbidden: "The API key does not have access to this model.",
    ModelErrorKind.model_not_found: "That model name was not found at the provider.",
    ModelErrorKind.context_too_long: "The conversation is longer than this model's context "
    "window. Start a new conversation or pick a model with a larger context.",
    ModelErrorKind.content_blocked: "The provider declined to answer this request.",
    ModelErrorKind.rate_limited: "The provider is rate-limiting or out of quota for this key.",
    ModelErrorKind.timeout: "The provider did not answer in time.",
    ModelErrorKind.unreachable: "Could not reach the provider. Check the base URL and your "
    "network.",
    ModelErrorKind.provider_error: "The provider returned an error. Check the model name and "
    "try again.",
    ModelErrorKind.internal: "The provider returned an error. Check the model name and try again.",
}


def workspace_message(exc: BaseException) -> str:
    return WORKSPACE_MESSAGES[classify(exc).kind]


def own_key_message(exc: BaseException) -> str:
    return OWN_KEY_MESSAGES[classify(exc).kind]
