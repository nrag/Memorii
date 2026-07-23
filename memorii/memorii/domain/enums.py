"""Canonical enums for Memorii v1 foundation."""

from enum import StrEnum


class MemoryDomain(StrEnum):
    TRANSCRIPT = "transcript"
    SEMANTIC = "semantic"
    EPISODIC = "episodic"
    USER = "user"
    EXECUTION = "execution"
    SOLVER = "solver"


class MemoryScope(StrEnum):
    GLOBAL = "global"
    USER = "user"
    TASK = "task"
    EXECUTION_NODE = "execution_node"
    STEP = "step"


class Durability(StrEnum):
    EPHEMERAL = "ephemeral"
    SESSION = "session"
    TASK_PERSISTENT = "task_persistent"
    LONG_TERM = "long_term"


class CommitStatus(StrEnum):
    CANDIDATE = "candidate"
    COMMITTED = "committed"
    ARCHIVED = "archived"


class MemoryRecordVisibility(StrEnum):
    RUNTIME_CONTEXT = "runtime_context"
    INTERNAL_CONTROL = "internal_control"


class SourceType(StrEnum):
    USER = "user"
    AGENT = "agent"
    TOOL = "tool"
    ENVIRONMENT = "environment"
    SYSTEM = "system"
    DERIVED = "derived"


class ExtractionRunStatus(StrEnum):
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    ABSTAINED = "abstained"
    FAILED = "failed"


class ProviderAttemptStatus(StrEnum):
    NOT_ATTEMPTED = "not_attempted"
    SUCCEEDED = "succeeded"
    PROVIDER_ERROR = "provider_error"
    INVALID_JSON = "invalid_json"
    SCHEMA_ERROR = "schema_error"


class FallbackOutcome(StrEnum):
    NOT_USED = "not_used"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class FinalExtractionSource(StrEnum):
    PRIMARY = "primary"
    FALLBACK = "fallback"
    NONE = "none"


class ExtractionFailureCode(StrEnum):
    PROVIDER_ERROR = "provider_error"
    INVALID_JSON = "invalid_json"
    SCHEMA_VALIDATION = "schema_validation"
    OUTPUT_VALIDATION = "output_validation"
    UNSUPPORTED_LANGUAGE = "unsupported_language"


class ExecutionNodeType(StrEnum):
    MISSION = "MISSION"
    WORK_ITEM = "WORK_ITEM"
    COMPONENT = "COMPONENT"
    INTERFACE = "INTERFACE"
    INVARIANT = "INVARIANT"
    TEST_SUITE = "TEST_SUITE"
    TEST_CASE = "TEST_CASE"
    ARTIFACT = "ARTIFACT"
    DECISION = "DECISION"
    RISK = "RISK"
    QUESTION = "QUESTION"
    DEFECT = "DEFECT"
    MILESTONE = "MILESTONE"
    CONSTRAINT = "CONSTRAINT"


class ExecutionEdgeType(StrEnum):
    DECOMPOSES_INTO = "DECOMPOSES_INTO"
    DEPENDS_ON = "DEPENDS_ON"
    BLOCKS = "BLOCKS"
    IMPLEMENTS = "IMPLEMENTS"
    VERIFIED_BY = "VERIFIED_BY"
    PRODUCES = "PRODUCES"
    CONSUMES = "CONSUMES"
    REQUIRES = "REQUIRES"
    CONSTRAINED_BY = "CONSTRAINED_BY"
    SUPERSEDES = "SUPERSEDES"
    RAISES = "RAISES"
    RESOLVES = "RESOLVES"
    AFFECTS = "AFFECTS"


class ExecutionNodeStatus(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    READY = "READY"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    DONE = "DONE"
    ARCHIVED = "ARCHIVED"


class SolverNodeType(StrEnum):
    GOAL = "GOAL"
    HYPOTHESIS = "HYPOTHESIS"
    COMPOSITE_HYPOTHESIS = "COMPOSITE_HYPOTHESIS"
    EXPLANATION_FACTOR = "EXPLANATION_FACTOR"
    OBSERVATION = "OBSERVATION"
    ACTION = "ACTION"
    ASSUMPTION = "ASSUMPTION"
    CONSTRAINT = "CONSTRAINT"
    SCENARIO = "SCENARIO"
    QUESTION = "QUESTION"
    SEMANTIC_REF = "SEMANTIC_REF"
    EPISODIC_REF = "EPISODIC_REF"
    USER_REF = "USER_REF"
    ENVIRONMENT_REF = "ENVIRONMENT_REF"
    SKILL_REF = "SKILL_REF"
    SYNTHESIS = "SYNTHESIS"


class SolverEdgeType(StrEnum):
    HAS_GOAL = "HAS_GOAL"
    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"
    TESTED_BY = "TESTED_BY"
    PRODUCES = "PRODUCES"
    REFINES = "REFINES"
    DEPENDS_ON = "DEPENDS_ON"
    CONTRIBUTES_TO = "CONTRIBUTES_TO"
    SYNTHESIZES_FROM = "SYNTHESIZES_FROM"
    VALID_UNDER = "VALID_UNDER"
    BLOCKS = "BLOCKS"
    RESOLVES = "RESOLVES"
    DERIVED_FROM = "DERIVED_FROM"
    REFERENCES = "REFERENCES"
    REOPENS = "REOPENS"
    EQUIVALENT_TO = "EQUIVALENT_TO"


class SolverNodeStatus(StrEnum):
    ACTIVE = "ACTIVE"
    PROMISING = "PROMISING"
    WEAKENED = "WEAKENED"
    DOMINATED = "DOMINATED"
    SUSPENDED = "SUSPENDED"
    FALSIFIED_UNDER_ASSUMPTIONS = "FALSIFIED_UNDER_ASSUMPTIONS"
    REOPENABLE = "REOPENABLE"
    RESOLVED = "RESOLVED"
    MERGED = "MERGED"
    ARCHIVED = "ARCHIVED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    NEEDS_TEST = "NEEDS_TEST"
    MULTIPLE_PLAUSIBLE_OPTIONS = "MULTIPLE_PLAUSIBLE_OPTIONS"


class SolverCreatedBy(StrEnum):
    MODEL = "model"
    TOOL = "tool"
    USER = "user"
    SYSTEM = "system"


class ConfidenceClass(StrEnum):
    OBSERVED = "observed"
    INFERRED = "inferred"
    SPECULATIVE = "speculative"
    RETRACTED = "retracted"


class TemporalValidityStatus(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    INVALIDATED = "invalidated"
    UNKNOWN = "unknown"


class EventType(StrEnum):
    TASK_STARTED = "TASK_STARTED"
    TASK_RESUMED = "TASK_RESUMED"
    TASK_PAUSED = "TASK_PAUSED"
    TASK_COMPLETED = "TASK_COMPLETED"
    TASK_ABORTED = "TASK_ABORTED"
    NODE_ADDED = "NODE_ADDED"
    EDGE_ADDED = "EDGE_ADDED"
    NODE_COMMITTED = "NODE_COMMITTED"
    EDGE_COMMITTED = "EDGE_COMMITTED"
    BELIEF_UPDATED = "BELIEF_UPDATED"
    STATUS_UPDATED = "STATUS_UPDATED"
    NODE_REOPENED = "NODE_REOPENED"
    NODE_MERGED = "NODE_MERGED"
    JUSTIFICATION_INVALIDATED = "JUSTIFICATION_INVALIDATED"
    SOLVER_STARTED = "SOLVER_STARTED"
    SOLVER_RESOLVED = "SOLVER_RESOLVED"
    OBSERVATION_RECEIVED = "OBSERVATION_RECEIVED"
    ACTION_SELECTED = "ACTION_SELECTED"
    ACTION_COMPLETED = "ACTION_COMPLETED"
