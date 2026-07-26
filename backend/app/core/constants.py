"""Cross-cutting constants.

Values that domain rules depend on (scoring weights, category vocabularies) belong in
`app/domain`, not here. This module holds only infrastructure-level constants.
"""

from typing import Final

#: Base URI for RFC 7807 `type` fields. Each problem appends its own slug.
PROBLEM_TYPE_BASE: Final = "https://bidpilot.dev/problems"

#: Header used to correlate a request across API logs, worker logs, and error responses.
REQUEST_ID_HEADER: Final = "X-Request-ID"

#: An inbound request ID is echoed back, so its length and character set are bounded to
#: keep hostile input out of logs and response headers.
REQUEST_ID_MAX_LENGTH: Final = 64

#: Media type mandated by RFC 7807 for problem responses.
PROBLEM_JSON_MEDIA_TYPE: Final = "application/problem+json"

#: A placeholder secret must never reach a deployed environment.
MIN_JWT_SECRET_LENGTH: Final = 32

#: Signing algorithm for access tokens. Pinned explicitly: accepting the algorithm named in
#: an untrusted token's own header is a classic JWT vulnerability.
JWT_ALGORITHM: Final = "HS256"

#: `typ` claim value. Refresh tokens are opaque random strings, never JWTs, so a token that
#: claims any other type is rejected rather than trusted for API access.
ACCESS_TOKEN_TYPE: Final = "access"  # noqa: S105 - a claim value, not a credential

#: Refresh tokens carry 48 random bytes (384 bits) of entropy.
REFRESH_TOKEN_BYTES: Final = 48

#: Upper bound on an accepted password. Argon2 handles long inputs, but an unbounded field
#: lets a caller burn server CPU on hashing.
MAX_PASSWORD_LENGTH: Final = 128
