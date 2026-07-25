"""Licensing and provenance audit for persona packs.

Called by `scripts/audit_persona.py` (built later) and by the pre-commit hook
so no pack ships without every asset documented. The rules encoded here come
directly from PERSONA-SCHEMA.md §8:

    * every asset must have source + license documented
    * ai_generated assets must name their generator
    * royalty_free / licensed assets must carry attribution or a url
    * no placeholder / n/a values allowed in shipped packs
    * only CC0, MIT, or Aether-owned licenses permitted

This module is intentionally pure: it takes a `PersonaPack` (already loaded
and schema-validated by the loader) and returns a list of human-readable
issue strings. Empty list = clean pack, safe to ship.
"""

from __future__ import annotations

from src.personas.models import AssetProvenance, AssetSource, PersonaPack

# Required asset keys in metadata.yaml (schema §4). Kept in sync with the
# validator in `PersonaMetadata._required_asset_keys`.
_REQUIRED_ASSET_KEYS: tuple[str, ...] = (
    "portrait",
    "state_images",
    "voice_reference",
    "voice_sample",
)

# Licenses permitted for shipped packs (schema §8). Match is case-insensitive.
# Exact strings in metadata.yaml must be one of these (normalised).
_ALLOWED_SHIPPING_LICENSES: frozenset[str] = frozenset(
    {
        "cc0",
        "mit",
        "custom_aether",  # Aether-owned, bundled under MIT umbrella
    }
)

# Values that indicate unresolved placeholder data — always flagged.
_PLACEHOLDER_TOKENS: frozenset[str] = frozenset({"", "n/a", "tbd", "todo", "unknown"})


def audit_pack(pack: PersonaPack) -> list[str]:
    """Return a list of shipping-blocker issues for `pack`.

    An empty list means the pack passes PERSONA-SCHEMA.md §8. A non-empty list
    must be surfaced to the caller (pre-commit hook, CI, CLI) and the pack
    must not be bundled until every issue is resolved.

    Args:
        pack: A schema-validated pack (typically produced by `scan_personas`).

    Returns:
        A list of human-readable issue strings. Each string names the asset
        key and the violated rule so the author can fix it without re-reading
        the schema.
    """
    issues: list[str] = []

    metadata = pack.metadata
    assets = metadata.assets

    # Required keys are enforced by PersonaMetadata, but defensive-repeat so
    # audit_pack works on any PersonaPack (including hand-constructed ones
    # from tests or programmatic pack builders).
    for key in _REQUIRED_ASSET_KEYS:
        if key not in assets:
            issues.append(f"metadata.assets.{key}: missing (required by PERSONA-SCHEMA.md §4)")

    for key, asset in assets.items():
        issues.extend(_audit_asset(key, asset))

    # Creator attribution — section §8 requires it on bundled packs.
    if _is_placeholder(metadata.creator):
        issues.append(f"metadata.creator: placeholder value '{metadata.creator}' — must name a real author")

    return issues


def _audit_asset(key: str, asset: AssetProvenance) -> list[str]:
    """Audit a single asset entry. Pure — returns a list of issue strings."""
    issues: list[str] = []
    prefix = f"metadata.assets.{key}"

    # License presence + allowlist.
    if _is_placeholder(asset.license):
        issues.append(f"{prefix}.license: placeholder value '{asset.license}' — document the real license")
    elif asset.license.strip().lower() not in _ALLOWED_SHIPPING_LICENSES:
        issues.append(
            f"{prefix}.license: '{asset.license}' is not in the shipping allowlist "
            f"{sorted(_ALLOWED_SHIPPING_LICENSES)} (see PERSONA-SCHEMA.md §8)"
        )

    # Source-specific obligations (schema §4, §8).
    if asset.source == AssetSource.PLACEHOLDER:
        issues.append(f"{prefix}.source: 'placeholder' is not shippable — replace before bundling")
    elif asset.source == AssetSource.AI_GENERATED:
        if _is_placeholder(asset.generator):
            issues.append(
                f"{prefix}.generator: ai_generated asset must name its generator "
                f"(model / pipeline / LoRA version)"
            )
    elif asset.source == AssetSource.ROYALTY_FREE:
        if _is_placeholder(asset.attribution) and _is_placeholder(asset.url):
            issues.append(
                f"{prefix}: royalty_free asset must carry attribution or a source url"
            )
    elif asset.source == AssetSource.LICENSED:
        if _is_placeholder(asset.attribution):
            issues.append(f"{prefix}.attribution: licensed asset must name the licensor")

    # Description is optional in the schema, but §8 implies "documented" =
    # enough context for a reviewer. We surface as a soft issue (still
    # blocks ship) only when the asset is neither ai_generated nor synthesized,
    # since those two are self-describing via generator/source.
    if asset.source in {AssetSource.ROYALTY_FREE, AssetSource.LICENSED, AssetSource.USER_SUPPLIED}:
        if asset.description is None or _is_placeholder(asset.description):
            issues.append(
                f"{prefix}.description: required for source={asset.source.value} "
                f"— describe what the asset is for reviewer context"
            )

    return issues


def _is_placeholder(value: str | None) -> bool:
    """True if `value` is None, empty, whitespace, or a known placeholder token."""
    if value is None:
        return True
    normalised = value.strip().lower()
    return normalised in _PLACEHOLDER_TOKENS


__all__ = ["audit_pack"]
