use aether_l4_router::*;

#[test]
fn seven_router_tiers_named() {
    let _all = [
        RouterTier::Reflex,
        RouterTier::LocalTiny,
        RouterTier::LocalSmall,
        RouterTier::LocalFull,
        RouterTier::RemoteStandard,
        RouterTier::RemotePremium,
        RouterTier::RemoteDeepResearch,
    ];
    assert_eq!(_all.len(), 7);
}
