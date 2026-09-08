"""Independent acceptance-only certification boundary.

Production code must not import this package.  The package consumes serialized
contracts and the public canonical typed-value codec to independently evaluate
bound statistical certification inputs.
"""

from acceptance.statistical_certification import (
    Certificate,
    HeldBinding,
    PreverifiedNumericCertificationContext,
    PreverifiedNumericGate,
    TransportLimits,
    WireRejected,
    evaluate_certificate,
    verify_certificate,
)

__all__ = [
    "Certificate",
    "HeldBinding",
    "PreverifiedNumericCertificationContext",
    "PreverifiedNumericGate",
    "TransportLimits",
    "WireRejected",
    "evaluate_certificate",
    "verify_certificate",
]
