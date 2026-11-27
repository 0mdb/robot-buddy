//! Byte-for-byte compatibility with the Pi supervisor (`supervisor/devices/protocol.py`), using
//! vectors that `gen_vectors.py` writes from the supervisor's own builders.

use reflex_core::protocol::{self, Command, Version, build, parse};

fn hex(s: &str) -> Vec<u8> {
    if s == "-" {
        return Vec::new();
    }
    (0..s.len()).step_by(2).map(|i| u8::from_str_radix(&s[i..i + 2], 16).unwrap()).collect()
}

#[test]
fn supervisor_vectors() {
    let text = include_str!("vectors.txt");
    let mut n = 0;
    for l in text.lines().filter(|l| !l.starts_with('#') && !l.is_empty()) {
        let f: Vec<&str> = l.split(' ').collect();
        let version = if f[1] == "1" { Version::V1 } else { Version::V2 };
        let frame = hex(f[2]);
        let ty = u8::from_str_radix(f[3], 16).unwrap();
        let seq = u32::from_str_radix(f[4], 16).unwrap();
        let t = u64::from_str_radix(f[5], 16).unwrap();
        let payload = hex(f[6]);

        // Parse what the supervisor built (or what the MCU must emit).
        assert_eq!(*frame.last().unwrap(), 0, "{l}");
        let mut buf = [0u8; 128];
        let p = parse(version, &frame[..frame.len() - 1], &mut buf).unwrap_or_else(|| panic!("parse: {l}"));
        assert_eq!((p.ty, p.seq, p.t_src_us, p.data), (ty, seq, t, &payload[..]), "{l}");

        // Rebuild: must be identical bytes in both directions.
        let mut out = [0u8; 128];
        let k = build(version, ty, seq, t, &payload, &mut out).unwrap();
        assert_eq!(&out[..k], &frame[..], "build: {l}");

        if f[0] == "h2m" {
            assert!(!matches!(Command::decode(&p), Command::Ignored { .. }), "decoded as ignored: {l}");
        }
        n += 1;
    }
    assert!(n >= 15, "only {n} vectors");
}

#[test]
fn state_payload_matches_supervisor_layout() {
    // Same values as gen_vectors.py's STATE rows.
    let s = protocol::State {
        speed_l_mm_s: 120,
        speed_r_mm_s: -118,
        gyro_z_mrad_s: -35,
        accel_x_mg: 12,
        accel_y_mg: -4,
        accel_z_mg: 1003,
        fault_flags: 0x0042,
        range_mm: 287,
        range_status: 0,
        cmd_seq_last_applied: 4242,
        t_cmd_applied_us: 99_000_001,
    };
    let text = include_str!("vectors.txt");
    for (ver, want_len) in [(Version::V1, 17), (Version::V2, 25)] {
        let tag = if ver == Version::V1 { "m2h 1 " } else { "m2h 2 " };
        let row = text.lines().find(|l| l.starts_with(tag) && l.split(' ').nth(3) == Some("80")).unwrap();
        let want = hex(row.split(' ').nth(6).unwrap());
        let mut b = [0u8; protocol::State::LEN_V2];
        let n = s.write(ver, &mut b);
        assert_eq!(n, want_len);
        assert_eq!(&b[..n], &want[..]);
    }
}
