"""Immutable ordered Merkle accumulator for verified catalog materializations."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from hashlib import sha256

_DOMAIN = b"memorii.materialization-accumulator.v1\x00"
_EMPTY_DIGEST = sha256(_DOMAIN + b"empty").digest()
_DIGEST_LENGTH = len(_EMPTY_DIGEST)


def _frame(value: bytes) -> bytes:
    return len(value).to_bytes(8, "big") + value


def row_value_digest(value: bytes) -> bytes:
    """Hash encoded row bytes without retaining large values in the tree."""
    digest = sha256(_DOMAIN + b"value\x00")
    digest.update(value)
    return digest.digest()


def _priority(key: bytes) -> bytes:
    return sha256(_DOMAIN + b"priority\x00" + key).digest()


@dataclass(frozen=True, slots=True)
class _Node:
    key: bytes
    value_digest: bytes
    priority: bytes
    left: _Node | None
    right: _Node | None
    count: int
    digest: bytes


def _root_digest(node: _Node | None) -> bytes:
    return _EMPTY_DIGEST if node is None else node.digest


def _count(node: _Node | None) -> int:
    return 0 if node is None else node.count


def _node(
    key: bytes, value_digest: bytes, priority: bytes, left: _Node | None = None, right: _Node | None = None,
) -> _Node:
    count = 1 + _count(left) + _count(right)
    digest = sha256(
        _DOMAIN + b"node\x00" + _frame(key) + value_digest
        + _root_digest(left) + _root_digest(right) + count.to_bytes(8, "big")
    ).digest()
    return _Node(key, value_digest, priority, left, right, count, digest)


def _children(node: _Node, left: _Node | None, right: _Node | None) -> _Node:
    return _node(node.key, node.value_digest, node.priority, left, right)


def _replace_child(node: _Node, child: _Node | None, *, was_left: bool) -> _Node:
    if was_left:
        return _children(node, child, node.right)
    return _children(node, node.left, child)


def _merge(left: _Node | None, right: _Node | None) -> _Node | None:
    """Join two ordered subtrees, reusing their untouched branches."""
    path: list[tuple[_Node, bool]] = []
    while left is not None and right is not None:
        if (left.priority, left.key) < (right.priority, right.key):
            path.append((left, False))
            left = left.right
        else:
            path.append((right, True))
            right = right.left
    merged = left if left is not None else right
    for parent, was_left in reversed(path):
        merged = _replace_child(parent, merged, was_left=was_left)
    return merged


@dataclass(frozen=True, slots=True)
class MaterializationAccumulator:
    """Canonical Cartesian tree with deterministic, hash-distributed priorities.

    In-order traversal follows the encoded primary keys. Key-derived priorities
    make a specific set of rows produce one shape, independent of mutation order.
    Changed rows replace only their search paths, leaving the prior tree intact
    for publication failure or rollback.
    """

    _root: _Node | None = None

    @classmethod
    def empty(cls) -> MaterializationAccumulator:
        return cls()

    @classmethod
    def from_sorted_rows(cls, rows: Iterable[tuple[bytes, bytes]]) -> MaterializationAccumulator:
        return cls.from_sorted_digests((key, row_value_digest(value)) for key, value in rows)

    @classmethod
    def from_sorted_digests(cls, rows: Iterable[tuple[bytes, bytes]]) -> MaterializationAccumulator:
        """Build in one pass in time linear in the number of sorted leaves."""
        spine: list[tuple[bytes, bytes, bytes, _Node | None]] = []
        previous_key: bytes | None = None
        for key, value_digest in rows:
            if previous_key is not None and key <= previous_key:
                raise ValueError("materialization keys must be strictly increasing")
            if len(value_digest) != _DIGEST_LENGTH:
                raise ValueError("invalid materialization row digest length")
            previous_key = key
            priority = _priority(key)
            left = None
            while spine and (priority, key) < (spine[-1][2], spine[-1][0]):
                prior_key, prior_value, prior_priority, prior_left = spine.pop()
                left = _node(prior_key, prior_value, prior_priority, prior_left, left)
            spine.append((key, value_digest, priority, left))
        right = None
        for key, value_digest, priority, left in reversed(spine):
            right = _node(key, value_digest, priority, left, right)
        return cls(right)

    @property
    def row_count(self) -> int:
        return _count(self._root)

    def catalog_digest(self, catalog: str) -> str:
        return sha256(_DOMAIN + b"catalog\x00" + _frame(catalog.encode("utf-8")) + _root_digest(self._root)).hexdigest()

    def lookup_digest(self, key: bytes) -> bytes | None:
        node = self._root
        while node is not None:
            if key == node.key:
                return node.value_digest
            node = node.left if key < node.key else node.right
        return None

    def _search(self, key: bytes) -> tuple[_Node | None, list[tuple[_Node, bool]]]:
        path: list[tuple[_Node, bool]] = []
        node = self._root
        while node is not None and key != node.key:
            was_left = key < node.key
            path.append((node, was_left))
            node = node.left if was_left else node.right
        return node, path

    def upsert(self, key: bytes, value: bytes) -> MaterializationAccumulator:
        return self.upsert_digest(key, row_value_digest(value))

    def upsert_digest(self, key: bytes, value_digest: bytes) -> MaterializationAccumulator:
        if len(value_digest) != _DIGEST_LENGTH:
            raise ValueError("invalid materialization row digest length")
        current, path = self._search(key)
        if current is not None and current.value_digest == value_digest:
            return self
        if current is None:
            updated = _node(key, value_digest, _priority(key))
        else:
            updated = _node(key, value_digest, current.priority, current.left, current.right)
        for parent, was_left in reversed(path):
            if (updated.priority, updated.key) >= (parent.priority, parent.key):
                updated = _replace_child(parent, updated, was_left=was_left)
            elif was_left:
                rotated_parent = _children(parent, updated.right, parent.right)
                updated = _children(updated, updated.left, rotated_parent)
            else:
                rotated_parent = _children(parent, parent.left, updated.left)
                updated = _children(updated, rotated_parent, updated.right)
        return MaterializationAccumulator(updated)

    def delete(self, key: bytes) -> MaterializationAccumulator:
        current, path = self._search(key)
        if current is None:
            raise KeyError(key)
        updated = _merge(current.left, current.right)
        for parent, was_left in reversed(path):
            updated = _replace_child(parent, updated, was_left=was_left)
        return MaterializationAccumulator(updated)
