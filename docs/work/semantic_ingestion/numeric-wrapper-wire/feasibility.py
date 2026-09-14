"""Proposal-only byte-form experiment; never imported by production."""
import json
from hashlib import sha256


def encode(fields):
    return json.dumps({'$type': 'map', 'entries': sorted(fields.items())}, separators=(',', ':'), ensure_ascii=False).encode('utf-8')


def decode(raw, kind, spec_id='example.quantity.v1'):
    tree = json.loads(raw)
    assert isinstance(tree, dict) and set(tree) == {'$type', 'entries'}
    assert tree['$type'] == 'map'
    entries = tree['entries']
    assert isinstance(entries, list)
    assert all(isinstance(item, list) and len(item) == 2 and all(isinstance(value, str) for value in item) for item in entries)
    fields = dict(entries)
    assert len(fields) == len(entries) and encode(fields) == raw
    if kind == 'binary64':
        assert set(fields) == {'ieee754_hex'}
        value = fields['ieee754_hex']
        assert len(value) == 16 and all(c in '0123456789abcdef' for c in value)
        bits = int(value, 16)
        assert ((bits >> 52) & 2047) != 2047 and bits != 1 << 63
    else:
        assert set(fields) == {'encoding_spec_id', 'fixed_scale_value'}
        assert fields['encoding_spec_id'] == spec_id
        value = fields['fixed_scale_value']
        unsigned = value.removeprefix('-')
        integer, sep, fraction = unsigned.partition('.')
        assert sep and integer and fraction and integer.isascii() and fraction.isascii()
        assert integer.isdigit() and fraction.isdigit() and len(fraction) == 2
        assert len(integer) == 1 or not integer.startswith('0')
        assert not value.startswith('-') or any(c != '0' for c in integer + fraction)
    return fields


binary = b'{"$type":"map","entries":[["ieee754_hex","3ff0000000000000"]]}'
decimal = b'{"$type":"map","entries":[["encoding_spec_id","example.quantity.v1"],["fixed_scale_value","1.25"]]}'
assert encode({'ieee754_hex':'3ff0000000000000'}) == binary
assert encode({'encoding_spec_id':'example.quantity.v1','fixed_scale_value':'1.25'}) == decimal
positive = [(binary, 'binary64'), (decimal, 'decimal')]
positive += [(encode({'ieee754_hex': value}), 'binary64') for value in ('0000000000000000','0000000000000001','bff0000000000000')]
for raw, kind in positive:
    assert encode(decode(raw, kind)) == raw
negative = [(encode({'ieee754_hex': value}), 'binary64') for value in ('7ff0000000000000','fff0000000000000','7ff8000000000000','8000000000000000','3FF0000000000000')]
negative += [(encode({'encoding_spec_id':'example.quantity.v1','fixed_scale_value': value}), 'decimal') for value in ('+1.25','01.25','1.2','1.250','1e2','-0.00')]
negative += [(encode({'encoding_spec_id':'other','fixed_scale_value':'1.25'}), 'decimal'), (binary+b'\n','binary64'), (encode({'ieee754_hex':'3ff0000000000000','extra':'x'}),'binary64')]
for raw, kind in negative:
    try:
        decode(raw, kind)
    except (AssertionError, ValueError):
        pass
    else:
        raise AssertionError('negative vector accepted')
print(json.dumps({'scope':'proposal-only exact-map feasibility, not production codec or independent compiler parity','positive':len(positive),'negative':len(negative),'binary64_sha256':sha256(binary).hexdigest(),'decimal_sha256':sha256(decimal).hexdigest()}, indent=2))
