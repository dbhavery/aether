use aether_l2_memory::*;

#[test]
fn six_memory_domains_named() {
    let _all = [
        MemoryDomain::Personal,
        MemoryDomain::Work,
        MemoryDomain::Health,
        MemoryDomain::Finance,
        MemoryDomain::Creative,
        MemoryDomain::System,
    ];
    assert_eq!(_all.len(), 6);
}

#[test]
fn provenance_tag_set_matches_l5_contract() {
    // These tags must match the L5 ProvenanceTag surface 1:1 — L5 consumes
    // them on every ActionRequest. Regenerate ts-rs bindings if this changes.
    let _all = [
        ProvenanceTag::Public,
        ProvenanceTag::Session,
        ProvenanceTag::Durable,
        ProvenanceTag::Private,
        ProvenanceTag::UntrustedInput,
        ProvenanceTag::ScrapedContent,
        ProvenanceTag::ExtractedPreference,
    ];
    assert_eq!(_all.len(), 7);
}
