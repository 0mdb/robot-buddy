"""policy.py: the parts a robot deploy depends on, checked without the sim."""

from __future__ import annotations

import numpy as np

import policy


def test_flat_roundtrip() -> None:
    x = np.random.default_rng(0).normal(size=policy.n_params())
    assert np.array_equal(policy.Mlp.from_flat(x).flat(), x)


def test_untrained_policy_drives_straight_at_patrol_speed() -> None:
    m = policy.Mlp.from_flat(policy.initial(155.0))
    obs = np.random.default_rng(1).normal(
        size=policy.N_OBS
    )  # weights are zero: obs is ignored
    assert policy.to_twist(m.act(obs)) == (155, 0)


def test_twist_mapping_inverts() -> None:
    for v, w in ((-150, -1500), (0, 0), (300, 1500), (120, -400)):
        assert policy.to_twist(policy.from_twist(v, w)) == (v, w)


def test_obs_shape_and_non_ok_range_reads_far() -> None:
    ob = policy.ObsBuilder()
    kw = dict(
        speed_l_mm_s=0,
        speed_r_mm_s=0,
        gyro_z_mrad_s=0,
        capped_v_mm_s=0,
        capped_w_mrad_s=0,
        tick_mono_ms=0.0,
    )
    o = ob.build(range_mm=500, range_status=policy.RANGE_OK, **kw)
    assert o.shape == (policy.N_OBS,)
    assert o[0] == 0.25 and o[len(policy.HISTORY_TICKS)] == 1.0
    o = ob.build(range_mm=0, range_status=3, **kw)
    assert o[0] == policy.RANGE_FAR and o[len(policy.HISTORY_TICKS)] == 0.0
    assert (
        o[1] == 0.25
    )  # one tick ago is still the 500 mm reading (history clamps to oldest)
