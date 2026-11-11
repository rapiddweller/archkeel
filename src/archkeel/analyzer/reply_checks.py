# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Check that a collector reply answers its request (AD-319)."""

from dataclasses import replace
from pathlib import PurePosixPath

from archkeel.analyzer.selected_scope import check_selected_files
from archkeel.ir.facts import (
    Language,
    ProviderBindingKind,
    ResolutionRole,
    SourceFacts,
    SourceProfile,
)
from archkeel.ir.facts_codec import ProtocolError
from archkeel.ir.protocol import (
    FEATURE_GATED_PROTOCOLS,
    PYTHON_IMPORT_SURVEY_SECTIONS,
    CollectionRequest,
    CollectionResponse,
    ProtocolVersion,
    PythonCollectionPhase,
    PythonProviderSource,
    PythonSettings,
    collected_resolution_features,
)

PROVIDER_PREFIX = ".archkeel-providers"


def check_reply(
    response: CollectionResponse,
    request: CollectionRequest,
    *,
    protocol_version: ProtocolVersion | None,
    adapter_version: str | None,
) -> None:
    """Raise when the reply disagrees with its request or with a version the host pins."""
    if protocol_version is not None and response.protocol_version is not request.protocol_version:
        raise ProtocolError("collector response protocol version does not match its request")
    # A collector that the host starts from its own package must have the host version.
    reported = response.facts.adapter.version
    if adapter_version is not None and reported != adapter_version:
        raise ProtocolError(
            f"collector adapter version {reported[:64]!r} does not match "
            f"the host version {adapter_version!r}"
        )
    request = _as_collected(response, request)
    check_requested_facts(response.facts, request)
    check_provider_sources(response, request)


def _as_collected(response: CollectionResponse, request: CollectionRequest) -> CollectionRequest:
    """A full reply to a survey request is the one-process reply (AD-358): check it as a collection.

    The provider sources are the inputs that the reply lists; the collector checked them
    against its own survey before it replied.
    """
    resolver = request.resolver
    if not (
        isinstance(resolver, PythonSettings)
        and resolver.phase is PythonCollectionPhase.PROVIDERS
        and frozenset(response.facts.capabilities.sections)
        != frozenset(PYTHON_IMPORT_SURVEY_SECTIONS)
    ):
        return request
    listed: list[PythonProviderSource] = []
    for item in response.facts.inputs:
        path: str = item.path
        if path.startswith(PROVIDER_PREFIX + "/") and item.role is ResolutionRole.RESOLUTION:
            listed.append(_listed_provider(path, item.digest))
    return replace(
        request,
        resolver=replace(
            resolver, phase=PythonCollectionPhase.COLLECT, provider_sources=tuple(listed)
        ),
    )


def _listed_provider(path: str, digest: str) -> PythonProviderSource:
    relative: str = path.removeprefix(PROVIDER_PREFIX + "/")
    parts: list[str] = relative.split("/")
    leaf: str = parts.pop()
    if leaf != "__init__.py":
        parts.append(leaf.removesuffix(".py"))
    return PythonProviderSource(".".join(parts), path, "", digest)


def check_provider_sources(response: CollectionResponse, request: CollectionRequest) -> None:
    """Raise when the captured provider sources disagree with the discovery inputs."""
    discovery = (
        isinstance(request.resolver, PythonSettings)
        and request.resolver.phase is PythonCollectionPhase.PROVIDERS
    )
    expected = {
        item.path: item.digest
        for item in response.facts.inputs
        if item.path.startswith(".archkeel-providers/")
    }
    captured = {item.path: item.digest for item in response.provider_sources}
    if (discovery and captured != expected) or (not discovery and captured):
        raise ProtocolError("collector captured provider sources disagree with discovery inputs")


def check_requested_facts(facts: SourceFacts, request: CollectionRequest) -> None:
    """Raise when the facts disagree with the language, phase, snapshot or providers asked for."""
    profiles: dict[Language, SourceProfile] = {
        Language.PYTHON: SourceProfile.PYTHON,
        Language.DART: SourceProfile.DART,
        Language.TYPESCRIPT: SourceProfile.TYPESCRIPT,
        Language.RUST: SourceProfile.RUST,
    }
    if facts.profile != profiles[request.resolver.language]:
        raise ProtocolError("collector profile disagrees with requested language")
    if (
        isinstance(request.resolver, PythonSettings)
        and request.resolver.phase is not PythonCollectionPhase.COLLECT
        and frozenset(facts.capabilities.sections) != frozenset(PYTHON_IMPORT_SURVEY_SECTIONS)
    ):
        raise ProtocolError("collector sections disagree with requested import survey")
    if (
        request.protocol_version in FEATURE_GATED_PROTOCOLS
        and isinstance(request.resolver, PythonSettings)
        and request.resolver.phase is PythonCollectionPhase.COLLECT
        and frozenset(facts.capabilities.resolution_features)
        != frozenset(
            collected_resolution_features(request.protocol_version, request.resolver.features)
        )
    ):
        raise ProtocolError("collector resolution features disagree with requested features")
    if (
        facts.source.git_head != request.snapshot.git_head
        or facts.source.dirty != request.snapshot.dirty
    ):
        raise ProtocolError("collector facts disagree with requested snapshot")
    check_selected_files(facts, request)
    providers = (
        request.resolver.provider_sources if isinstance(request.resolver, PythonSettings) else ()
    )
    discovery = (
        isinstance(request.resolver, PythonSettings)
        and request.resolver.phase is PythonCollectionPhase.PROVIDERS
    )
    expected = {item.path: item.digest for item in providers}
    actual: dict[str, str] = {}
    for item in facts.inputs:
        path: str = item.path
        if path.startswith(".archkeel-providers/") and item.role is ResolutionRole.RESOLUTION:
            actual[path] = item.digest
    if (not discovery and actual != expected) or set(actual) & set(facts.coverage.selected_files):
        raise ProtocolError("collector provider sources disagree with requested snapshot")
    providers_by_path = {item.path: item for item in providers}
    evidence = {item.id: item for item in facts.evidence}
    for binding in facts.provider_bindings:
        if discovery:
            continue
        source = providers_by_path.get(evidence[binding.evidence_id].file)
        qualified_name: str = binding.qualified_name
        owner: str = qualified_name.rpartition(".")[0]
        source_matches = source is not None and (
            qualified_name == source.module
            if binding.kind is ProviderBindingKind.MODULE
            else owner == source.module
            # A package initializer can publish its child through sys.modules (collections.abc).
            or PurePosixPath(source.path).name == "__init__.py"
            and owner.rpartition(".")[0] == source.module
            if binding.kind is ProviderBindingKind.ALIAS
            else qualified_name.startswith(source.module + ".")
        )
        if not source_matches:
            raise ProtocolError("collector provider binding disagrees with requested source")
