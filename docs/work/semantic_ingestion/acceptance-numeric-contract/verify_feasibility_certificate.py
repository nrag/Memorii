"""Independent nonproduction verifier for the generated rational certificates."""

from fractions import Fraction
import json
from math import comb
from pathlib import Path


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def parse(text: str) -> Fraction:
    if not isinstance(text, str):
        raise ValueError("rational must be text")
    numerator, separator, denominator = text.partition("/")
    if not separator or not numerator or not denominator:
        raise ValueError("rational must have canonical numerator/denominator form")
    value = Fraction(int(numerator), int(denominator))
    if value.denominator <= 0 or f"{value.numerator}/{value.denominator}" != text:
        raise ValueError("rational is not canonical")
    return value


def binomial_tail(count: int, successes: int, probability: Fraction, tail: str) -> Fraction:
    if tail not in {"ge", "le"}:
        raise ValueError("unknown binomial tail")
    indices = range(successes, count + 1) if tail == "ge" else range(successes + 1)
    return sum((Fraction(comb(count, index)) * probability**index * (1 - probability) ** (count - index) for index in indices), Fraction())


def independently_enclose_exponential(exponent: Fraction, terms: int) -> tuple[Fraction, Fraction]:
    if exponent < 0 or not isinstance(terms, int) or terms < 1 or Fraction(terms + 2) <= exponent:
        raise ValueError("invalid exponential certificate")
    if exponent == 0:
        return Fraction(1), Fraction(1)
    term = partial_sum = Fraction(1)
    for index in range(1, terms + 1):
        term = term * exponent / index
        partial_sum += term
    omitted_first_term = term * exponent / (terms + 1)
    upper_sum = partial_sum + omitted_first_term / (1 - exponent / (terms + 2))
    return Fraction(1, 1) / upper_sum, Fraction(1, 1) / partial_sum


def validate_holm(raw: dict[str, Fraction], order: list[str]) -> None:
    require(bool(raw), "empty Holm family")
    require(len(order) == len(raw) and set(order) == set(raw), "invalid Holm family")
    require(order == sorted(raw, key=lambda claim: (raw[claim], claim)), "invalid Holm order")


def validate_alpha(alpha: Fraction) -> None:
    require(0 < alpha < 1, "alpha must be interior")


def validate_branch(branch: str) -> None:
    require(branch in {"exponential", "degenerate_fixed_value"}, "unknown Hoeffding branch")


def validate_contributions(contributions: list[object]) -> None:
    require(bool(contributions), "empty contribution evidence")


def mutation_proof() -> None:
    for bad in ("+1/2", "01/2", "2/4", "-0/1", "1/0"):
        try:
            parse(bad)
        except (ValueError, ZeroDivisionError):
            pass
        else:
            raise ValueError("noncanonical rational accepted")
    for bad_tail in ("unknown", "GE"):
        try:
            binomial_tail(1, 0, Fraction(1, 2), bad_tail)
        except ValueError:
            pass
        else:
            raise ValueError("unknown tail accepted")
    for bad_alpha in (Fraction(), Fraction(1)):
        try:
            validate_alpha(bad_alpha)
        except ValueError:
            pass
        else:
            raise ValueError("boundary alpha accepted")
    try:
        validate_branch("unknown")
    except ValueError:
        pass
    else:
        raise ValueError("unknown branch accepted")
    try:
        validate_contributions([])
    except ValueError:
        pass
    else:
        raise ValueError("empty evidence accepted")
    for bad_raw, bad_order in (({}, []), ({"a": Fraction(1, 2)}, ["b"])):
        try:
            validate_holm(bad_raw, bad_order)
        except ValueError:
            pass
        else:
            raise ValueError("invalid Holm family accepted")


def main() -> None:
    value = json.loads(Path(__file__).with_name("feasibility-result.json").read_text(encoding="ascii"))
    expected_top = {"algorithm", "binomial_root_certificates", "exponential_certificates", "holm_exact_tie_certificate", "independent_decimal_reference", "policy_or_activation_authority", "weighted_hoeffding_certificates"}
    require(set(value) == expected_top, "unknown or missing result field")
    require(value["algorithm"] == "nonproduction-rational-enclosure-feasibility-v2", "unknown algorithm")
    require(value["policy_or_activation_authority"] is False, "wrong authority")
    for certificate in value["binomial_root_certificates"]:
        require(set(certificate) == {"count", "successes", "tail", "alpha", "lower", "upper"}, "invalid binomial certificate fields")
        lower, upper, alpha = (parse(certificate[key]) for key in ("lower", "upper", "alpha"))
        require(certificate["tail"] in {"ge", "le"}, "unknown root tail")
        require(certificate["count"] > 0 and 0 <= certificate["successes"] <= certificate["count"], "invalid root domain")
        validate_alpha(alpha)
        require(lower < upper, "empty root interval")
        lower_tail = binomial_tail(certificate["count"], certificate["successes"], lower, certificate["tail"])
        upper_tail = binomial_tail(certificate["count"], certificate["successes"], upper, certificate["tail"])
        require((lower_tail <= alpha <= upper_tail) if certificate["tail"] == "ge" else (lower_tail >= alpha >= upper_tail), "root inequality failed")
    for certificate in value["weighted_hoeffding_certificates"]:
        require(set(certificate) == {"branch", "exponent", "lower", "margin", "squared_range_weight_sum", "terms", "upper"}, "invalid Hoeffding certificate fields")
        exponent, lower, upper, margin, squared_sum = (parse(certificate[key]) for key in ("exponent", "lower", "upper", "margin", "squared_range_weight_sum"))
        validate_branch(certificate["branch"])
        if certificate["branch"] == "degenerate_fixed_value":
            require(squared_sum == 0 and exponent == 0, "invalid degenerate branch")
            require((lower, upper) == ((Fraction(), Fraction()) if margin > 0 else (Fraction(1), Fraction(1))), "wrong degenerate outcome")
            continue
        require(certificate["branch"] == "exponential", "unknown Hoeffding branch")
        require(squared_sum > 0, "invalid weighted range sum")
        require(exponent == (Fraction() if margin <= 0 else 2 * margin * margin / squared_sum), "wrong exponent")
        require(0 < lower <= upper <= 1, "invalid probability interval")
        require((lower, upper) == independently_enclose_exponential(exponent, certificate["terms"]), "wrong exponential enclosure")
    for certificate in value["exponential_certificates"]:
        require(set(certificate) == {"exponent", "lower", "terms", "upper"}, "invalid exponential certificate fields")
        exponent, lower, upper = (parse(certificate[key]) for key in ("exponent", "lower", "upper"))
        require((lower, upper) == independently_enclose_exponential(exponent, certificate["terms"]), "wrong standalone enclosure")
    tie = value["holm_exact_tie_certificate"]
    require(set(tie) == {"canonical_order", "raw_p_values"}, "invalid tie certificate fields")
    raw = {claim: parse(probability) for claim, probability in tie["raw_p_values"].items()}
    validate_holm(raw, tie["canonical_order"])
    mutation_proof()
    print("independent certificate verification: passed")


if __name__ == "__main__":
    main()
