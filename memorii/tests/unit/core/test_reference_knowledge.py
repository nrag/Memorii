from memorii.core.memory_evolution import BuiltInReferenceKnowledgeProvider
from memorii.core.memory_evolution.models import EntityLinkState, EntityType
from memorii.core.memory_plane import MemoryPlaneService


def test_built_in_reference_entities_resolve_by_name_and_alias() -> None:
    provider = BuiltInReferenceKnowledgeProvider()

    paris = provider.find_entity("Paris")
    france = provider.find_entity("france")
    azure = provider.find_entity("Microsoft Azure")

    assert paris is not None
    assert paris.reference_id == "ref:city:paris"
    assert paris.entity_type == "city"
    assert france is not None
    assert france.reference_id == "ref:country:france"
    assert azure is not None
    assert azure.reference_id == "ref:cloud:azure"


def test_built_in_reference_claims_are_read_only_and_do_not_create_user_memory() -> None:
    plane = MemoryPlaneService()
    provider = BuiltInReferenceKnowledgeProvider()

    assert provider.claims()
    assert plane.list_records() == []


def test_project_scoped_alias_can_coexist_with_reference_entity() -> None:
    provider = BuiltInReferenceKnowledgeProvider()
    project_alias = EntityLinkState(
        link_id="link:project-paris",
        mention_text="Paris",
        canonical_entity_id="ent:project:paris",
        normalized_name="paris",
        entity_type=EntityType.PROJECT,
        aliases=["Paris"],
        confidence=0.8,
    )

    reference = provider.find_entity("Paris")

    assert reference is not None
    assert reference.reference_id == "ref:city:paris"
    assert project_alias.canonical_entity_id == "ent:project:paris"
    assert project_alias.canonical_entity_id != reference.reference_id
