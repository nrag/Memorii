# Numeric Source Consultation

Profile-3 decimal numeric roles require non-null unit, positive canonical scale,
lower/upper bounds, inclusivity flags and Boolean reject_inexact. Binary64 rows
require all these values null (observation design numeric-role grammar).

SIA section 3.15.1 defines CanonicalDecimalQuantity for bound values: optional
minus, integer digits without leading zero except zero, decimal point and
exactly the registered scale's fractional digits. Exponent, plus, negative zero
and omitted scale reject. The compiler must validate these lexical constraints
without introducing Python integer-conversion limits.

The generic role admits reject_inexact=false. It remains committed source data
and cannot override higher-precedence SIA's unconditional rejection of rounding.
No alternate rounding behavior or rejection of false is derived from its name.
The coordinator classified the consultation's initial blocking claim as
unsupported; the auditor agreed after checking source precedence. No external
decision or governing-document change is required.

SIA's strict lower<upper requirement in Policy and Resource Validity applies to
the named statistical, monitoring, resource, admission, queue, deadline and
overload policies. It is not a universal relation for arbitrary numeric wrapper
declarations. Domain validators enforce it where applicable; the compiler does
not invent a generic comparison rule. The generic source grammar also does not
require a nonempty unit string.
