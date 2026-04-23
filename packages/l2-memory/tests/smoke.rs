use aether_l2_memory::*;

#[test]
fn six_memory_domains_named() {
    // Memory V2 §1 — six domains. ADR-0001 relocated this enum from
    // the shell to L2; the variant set is frozen.
    let all = [
        MemoryDomain::Session,
        MemoryDomain::Durable,
        MemoryDomain::Facts,
        MemoryDomain::Projects,
        MemoryDomain::Preferences,
        MemoryDomain::Artifacts,
    ];
    assert_eq!(all.len(), 6);
    assert_eq!(MemoryDomain::ALL.len(), 6);
    for (a, b) in all.iter().zip(MemoryDomain::ALL.iter()) {
        assert_eq!(a, b);
    }
}
