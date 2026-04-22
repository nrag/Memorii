"""Deterministic multilingual template rendering for long-horizon fixtures."""

from __future__ import annotations


def render_fact_statement(*, language: str, entity: str, attribute: str, value: str, template_id: str) -> str:
    templates = {
        "en": {
            "current_fact_statement": "{entity} now uses {value} for {attribute}.",
            "stale_fact_statement": "Previously, {entity} used {value} for {attribute}.",
            "wrong_attribute_statement": "{entity} uses {value} for {attribute}.",
        },
        "es": {
            "current_fact_statement": "{entity} ahora usa {value} para {attribute}.",
            "stale_fact_statement": "Antes, {entity} usaba {value} para {attribute}.",
            "wrong_attribute_statement": "{entity} usa {value} para {attribute}.",
        },
        "fr": {
            "current_fact_statement": "{entity} utilise maintenant {value} pour {attribute}.",
            "stale_fact_statement": "Avant, {entity} utilisait {value} pour {attribute}.",
            "wrong_attribute_statement": "{entity} utilise {value} pour {attribute}.",
        },
    }
    language_templates = templates.get(language, templates["en"])
    template = language_templates[template_id]
    return template.format(entity=entity, attribute=attribute, value=value)
