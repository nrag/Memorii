"""Spanish semantic evidence capabilities for memory extraction."""

from __future__ import annotations

from memorii.core.memory_evolution.language_support.base import (
    FrameLanguageCapabilities,
    ModalityLexicon,
    SemanticFrame,
)
from memorii.core.memory_evolution.language_support.contracts import EvidenceDecision, SourceEvidence


class SpanishExtractionCapabilities(FrameLanguageCapabilities):
    capability_id = "memory-extraction/es@1"
    language_codes = frozenset({"es", "spa"})
    negations = frozenset({("no",), ("nunca",), ("jamás",), ("ni",), ("tampoco",)})
    relation_type_hints = {
        "owner": (None, "person"),
        "approver": (None, "person"),
        "api_owner": (None, "person"),
        "dependency": (None, None),
    }
    modality_lexicon = ModalityLexicon(
        question_prefixes=(
            "quién",
            "quien",
            "qué",
            "que",
            "cuándo",
            "cuando",
            "dónde",
            "donde",
            "por qué",
            "por que",
            "cómo",
            "como",
            "es",
            "son",
            "puede",
            "podría",
            "podria",
            "debería",
            "deberia",
        ),
        hypothetical_markers=(
            "supongamos",
            "hipotéticamente",
            "hipoteticamente",
            "imagina",
            "si",
            "qué pasaría si",
            "que pasaria si",
            "podría ser",
            "podria ser",
        ),
        quoted_or_pasted_markers=("pegado", "pegar", "aquí hay un documento", "aqui hay un documento", "documento"),
        correction_markers=(
            "corrección",
            "correccion",
            "corrigiendo",
            "en realidad",
            "en cambio",
            "debería ser",
            "deberia ser",
        ),
        third_party_markers=(
            "dice",
            "dijo",
            "según",
            "segun",
            "el documento dice",
            "la transcripción dice",
            "la transcripcion dice",
            "supuestamente",
            "presuntamente",
            "aparentemente",
        ),
        instruction_prefixes=("por favor", "puedes", "podrías", "podrias", "recuerda", "no hagas"),
    )
    denial_markers = (
        "es falso que",
        "no es cierto que",
        "niega que",
        "negó que",
        "nego que",
    )
    clause_boundaries = ("pero", "sin embargo", "en cambio")
    dependency_markers = ("depende de", "requiere", "es dependiente de")
    blocking_markers = ("bloqueado por", "bloqueada por", "bloquea")
    relation_frames = {
        "owner": (
            SemanticFrame(
                ("object", "trigger", "subject"),
                ("posee", "es propietario de", "es propietaria de", "es responsable de", "está a cargo de"),
            ),
            SemanticFrame(
                ("subject", "trigger", "object"), ("pertenece a", "es propiedad de", "propietario es", "propietaria es")
            ),
            SemanticFrame(
                ("trigger", "subject", "object"), ("el propietario de", "la propietaria de", "responsable de")
            ),
        ),
        "approver": (
            SemanticFrame(("object", "trigger", "subject"), ("aprueba", "es aprobador de", "es aprobadora de")),
            SemanticFrame(
                ("subject", "trigger", "object"),
                ("es aprobado por", "es aprobada por", "aprobador es", "aprobadora es"),
            ),
        ),
        "api_owner": (
            SemanticFrame(
                ("object", "trigger", "subject"),
                ("es responsable de la api de", "es propietario de la api de", "es propietaria de la api de"),
            ),
            SemanticFrame(
                ("subject", "trigger", "object"),
                ("responsable de api es", "propietario de api es", "propietaria de api es"),
            ),
        ),
        "dependency": (
            SemanticFrame(("subject", "trigger", "object"), ("depende de", "requiere", "es dependiente de")),
            SemanticFrame(("object", "trigger", "subject"), ("respalda", "es requerido por", "es requerida por")),
        ),
    }
    identity_frames = {
        "alias_of": (
            SemanticFrame(
                ("object", "trigger", "subject"), ("también se llama", "también conocido como", "también conocida como")
            ),
            SemanticFrame(("subject", "trigger", "object"), ("es un alias de", "es un alias para")),
        ),
        "same_as": (
            SemanticFrame(("subject", "trigger", "object"), ("es lo mismo que", "es idéntico a", "es idéntica a")),
        ),
        "split_from": (
            SemanticFrame(
                ("subject", "trigger", "object"),
                ("se separó de", "se dividió de", "fue separado de", "fue separada de"),
            ),
        ),
        "merged_into": (
            SemanticFrame(
                ("subject", "trigger", "object"),
                ("se fusionó en", "fue fusionado en", "fue fusionada en", "se consolidó en"),
            ),
        ),
    }
    entity_type_frames = {
        entity_type: (
            SemanticFrame(("subject", "trigger", "object"), ("es un", "es una", "es el", "es la", "es")),
            SemanticFrame(("trigger", "object", "subject"), ("el", "la")),
        )
        for entity_type in ("proyecto", "persona", "servicio", "tarea", "preferencia")
    }
    literal_frames = {
        "status": (
            SemanticFrame(
                ("subject", "trigger", "object"),
                ("estado es", "estado está", "es", "está", "permanece", "quedó"),
            ),
            SemanticFrame(("subject", "object"), gap_allowlists=(frozenset(),)),
        ),
        "action_state": (
            SemanticFrame(
                ("subject", "trigger", "object"),
                ("estado es", "estado está", "es", "está", "permanece", "quedó"),
            ),
            SemanticFrame(("subject", "object")),
        ),
        "preference": (
            SemanticFrame(("subject", "trigger", "object"), ("prefiere", "preferencia es", "le gusta")),
            SemanticFrame(("trigger", "object"), ("prefiere", "preferencia es", "le gusta")),
        ),
        "belief": (
            SemanticFrame(
                ("subject", "trigger", "object"),
                ("cree", "creencia es", "hipótesis es", "hipotesis es", "causa raíz es", "causa raiz es"),
            ),
            SemanticFrame(
                ("trigger", "object"),
                ("creencia es", "hipótesis es", "hipotesis es", "causa raíz es", "causa raiz es"),
            ),
        ),
        "correction": (
            SemanticFrame(
                ("subject", "trigger", "object"),
                ("corrección es", "correccion es", "corregido a", "corregida a", "debería ser", "deberia ser"),
            ),
            SemanticFrame(
                ("trigger", "object"),
                ("corrección es", "correccion es", "corregido a", "corregida a", "debería ser", "deberia ser"),
            ),
        ),
    }
    literal_value_aliases = {
        "status": {
            "started": ("iniciado", "iniciada", "comenzado", "comenzada"),
            "in progress": ("en progreso", "en curso"),
            "blocked": ("bloqueado", "bloqueada"),
            "resumed": ("reanudado", "reanudada"),
            "abandoned": ("abandonado", "abandonada"),
            "completed": ("completado", "completada", "terminado", "terminada"),
            "failed": ("fallido", "fallida"),
            "succeeded": ("exitoso", "exitosa"),
        },
        "action_state": {
            "started": ("iniciado", "iniciada", "comenzado", "comenzada"),
            "in progress": ("en progreso", "en curso"),
            "blocked": ("bloqueado", "bloqueada"),
            "resumed": ("reanudado", "reanudada"),
            "abandoned": ("abandonado", "abandonada"),
            "completed": ("completado", "completada", "terminado", "terminada"),
            "failed": ("fallido", "fallida"),
            "succeeded": ("exitoso", "exitosa"),
        },
    }

    _entity_type_terms = {
        "project": "proyecto",
        "person": "persona",
        "service": "servicio",
        "task": "tarea",
        "preference": "preferencia",
    }

    def verify_entity_type(
        self,
        *,
        evidence: SourceEvidence,
        entity_name: str,
        entity_type: str,
        known_entity_names: tuple[str, ...],
    ) -> EvidenceDecision:
        translated = self._entity_type_terms.get(entity_type)
        if translated is None:
            return super().verify_entity_type(
                evidence=evidence,
                entity_name=entity_name,
                entity_type=entity_type,
                known_entity_names=known_entity_names,
            )
        return self._verify_frames(
            evidence=evidence,
            frames=self.entity_type_frames[translated],
            subject_name=entity_name,
            object_name=translated,
            known_entity_names=known_entity_names,
            allow_reversal=False,
        )
