//! Reflex wire protocol, byte-compatible with `esp32-reflex/main/protocol.{h,cpp}` and
//! `supervisor/devices/protocol.py` (spec: `supervisor/PROTOCOL.md`).
//!
//! On the wire: `[COBS(payload)] 0x00`. Payload before COBS:
//! - v1: `[type:u8][seq:u8][data][crc16:u16-LE]`
//! - v2: `[type:u8][seq:u32-LE][t_src_us:u64-LE][data][crc16:u16-LE]`
//!
//! CRC is CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF) over everything before it.
//! The version starts at 1 and the host switches it with SET_PROTOCOL_VERSION.

/// Largest frame the ESP32 accepts from the host (`usb_rx.cpp` MAX_FRAME).
pub const MAX_RX_FRAME: usize = 128;
/// v2 header: type + seq + t_src_us.
pub const V2_HEADER: usize = 1 + 4 + 8;

// ---- Packet type IDs ----

pub mod cmd {
    // Common (shared with the face MCU)
    pub const TIME_SYNC_REQ: u8 = 0x06;
    pub const SET_PROTOCOL_VERSION: u8 = 0x07;
    // Reflex
    pub const SET_TWIST: u8 = 0x10;
    pub const STOP: u8 = 0x11;
    pub const ESTOP: u8 = 0x12;
    pub const SET_LIMITS: u8 = 0x13; // defined, not handled by the ESP32 firmware either
    pub const CLEAR_FAULTS: u8 = 0x14;
    pub const SET_CONFIG: u8 = 0x15;
}

pub mod tel {
    pub const STATE: u8 = 0x80;
    pub const BRINGUP_DIAG: u8 = 0x82;
    pub const TIME_SYNC_RESP: u8 = 0x86;
    pub const PROTOCOL_VERSION_ACK: u8 = 0x87;
}

/// Fault bits in `StatePayload::fault_flags` (`shared_state.h`, `protocol.py::Fault`).
pub mod fault {
    pub const CMD_TIMEOUT: u16 = 1 << 0;
    pub const ESTOP: u16 = 1 << 1;
    pub const TILT: u16 = 1 << 2;
    pub const STALL: u16 = 1 << 3;
    pub const IMU_FAIL: u16 = 1 << 4;
    pub const BROWNOUT: u16 = 1 << 5;
    pub const OBSTACLE: u16 = 1 << 6;
    /// v2 board: direction expander missing. On v3 (DRV8876): driver nFAULT.
    pub const MOTOR_DRV: u16 = 1 << 7;
}

/// `StatePayload::range_status` (`protocol.py::RangeStatus`).
pub mod range_status {
    pub const OK: u8 = 0;
    pub const TIMEOUT: u8 = 1;
    pub const OUT_OF_RANGE: u8 = 2;
    pub const NOT_READY: u8 = 3;
}

// ---- CRC + COBS ----

pub fn crc16(data: &[u8]) -> u16 {
    let mut crc: u16 = 0xFFFF;
    for &b in data {
        crc ^= (b as u16) << 8;
        for _ in 0..8 {
            crc = if crc & 0x8000 != 0 { (crc << 1) ^ 0x1021 } else { crc << 1 };
        }
    }
    crc
}

/// Worst-case COBS output length for `n` input bytes (without the 0x00 delimiter).
pub const fn cobs_max_len(n: usize) -> usize {
    n + n / 254 + 1
}

/// COBS-encode `src` into `dst`. Returns the encoded length, or `None` if `dst` is too small.
pub fn cobs_encode(src: &[u8], dst: &mut [u8]) -> Option<usize> {
    if dst.len() < cobs_max_len(src.len()) {
        return None;
    }
    let mut code_idx = 0;
    let mut write = 1;
    let mut code: u8 = 1;
    for &b in src {
        if b == 0 {
            dst[code_idx] = code;
            code_idx = write;
            write += 1;
            code = 1;
        } else {
            dst[write] = b;
            write += 1;
            code += 1;
            if code == 0xFF {
                dst[code_idx] = code;
                code_idx = write;
                write += 1;
                code = 1;
            }
        }
    }
    dst[code_idx] = code;
    Some(write)
}

/// COBS-decode `src` (no delimiter) into `dst`. `None` on a zero byte, truncation or overflow.
/// Matches the ESP32 decoder, including a trailing 0xFF block adding no implicit zero.
pub fn cobs_decode(src: &[u8], dst: &mut [u8]) -> Option<usize> {
    let mut read = 0;
    let mut write = 0;
    while read < src.len() {
        let code = src[read];
        read += 1;
        if code == 0 {
            return None;
        }
        for _ in 1..code {
            if read >= src.len() || write >= dst.len() {
                return None;
            }
            dst[write] = src[read];
            write += 1;
            read += 1;
        }
        if code < 0xFF && read < src.len() {
            if write >= dst.len() {
                return None;
            }
            dst[write] = 0;
            write += 1;
        }
    }
    Some(write)
}

// ---- Envelope ----

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[cfg_attr(feature = "defmt", derive(defmt::Format))]
pub enum Version {
    V1,
    V2,
}

/// Build a framed packet (COBS + 0x00) into `out`. v1 truncates `seq` to u8 and drops
/// `t_src_us`, as the ESP32's `packet_build_v2` does. Returns the frame length.
pub fn build(version: Version, ty: u8, seq: u32, t_src_us: u64, data: &[u8], out: &mut [u8]) -> Option<usize> {
    const MAX_RAW: usize = 64;
    let mut raw = [0u8; MAX_RAW];
    let hdr = match version {
        Version::V1 => {
            raw[0] = ty;
            raw[1] = seq as u8;
            2
        }
        Version::V2 => {
            raw[0] = ty;
            raw[1..5].copy_from_slice(&seq.to_le_bytes());
            raw[5..13].copy_from_slice(&t_src_us.to_le_bytes());
            V2_HEADER
        }
    };
    let body = hdr + data.len();
    if body + 2 > MAX_RAW {
        return None;
    }
    raw[hdr..body].copy_from_slice(data);
    let crc = crc16(&raw[..body]);
    raw[body..body + 2].copy_from_slice(&crc.to_le_bytes());
    let n = cobs_encode(&raw[..body + 2], out)?;
    if n >= out.len() {
        return None;
    }
    out[n] = 0;
    Some(n + 1)
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Packet<'a> {
    pub ty: u8,
    /// u32 in v2; the u8 zero-extended in v1.
    pub seq: u32,
    /// 0 in v1.
    pub t_src_us: u64,
    pub data: &'a [u8],
}

/// Parse one frame (COBS bytes without the 0x00 delimiter). Same rules as the ESP32's
/// `packet_parse`: at least 4 decoded bytes, CRC must match, v2 needs at least 15 bytes
/// (shorter frames under v2 fall back to the v1 layout, as the ESP32 does).
pub fn parse<'a>(version: Version, frame: &[u8], buf: &'a mut [u8]) -> Option<Packet<'a>> {
    if frame.is_empty() || frame.len() > buf.len() {
        return None;
    }
    let n = cobs_decode(frame, buf)?;
    if n < 4 {
        return None;
    }
    let crc_at = n - 2;
    let rx_crc = u16::from_le_bytes([buf[crc_at], buf[crc_at + 1]]);
    if rx_crc != crc16(&buf[..crc_at]) {
        return None;
    }
    let buf = &buf[..crc_at];
    if version == Version::V2 && n >= V2_HEADER + 2 {
        Some(Packet {
            ty: buf[0],
            seq: u32::from_le_bytes(buf[1..5].try_into().unwrap()),
            t_src_us: u64::from_le_bytes(buf[5..13].try_into().unwrap()),
            data: &buf[V2_HEADER..],
        })
    } else {
        Some(Packet { ty: buf[0], seq: buf[1] as u32, t_src_us: 0, data: &buf[2..] })
    }
}

/// Splits a byte stream into frames on 0x00, as `usb_rx_task` does: a frame longer than
/// `MAX_RX_FRAME` is discarded up to the next delimiter.
pub struct FrameAccumulator {
    buf: [u8; MAX_RX_FRAME],
    len: usize,
    discard: bool,
}

impl Default for FrameAccumulator {
    fn default() -> Self {
        Self::new()
    }
}

impl FrameAccumulator {
    pub const fn new() -> Self {
        Self { buf: [0; MAX_RX_FRAME], len: 0, discard: false }
    }

    /// Feed one byte. Returns a complete frame (without the delimiter) when one ends.
    pub fn push(&mut self, b: u8) -> Option<&[u8]> {
        if b == 0 {
            let done = self.len > 0 && !self.discard;
            let len = self.len;
            self.len = 0;
            self.discard = false;
            return if done { Some(&self.buf[..len]) } else { None };
        }
        if self.discard {
            return None;
        }
        if self.len < MAX_RX_FRAME {
            self.buf[self.len] = b;
            self.len += 1;
        } else {
            self.discard = true;
        }
        None
    }
}

// ---- Commands (host -> MCU) ----

#[derive(Clone, Copy, Debug, PartialEq)]
#[cfg_attr(feature = "defmt", derive(defmt::Format))]
pub enum Command {
    SetProtocolVersion(u8),
    TimeSyncReq { ping_seq: u32 },
    SetTwist { v_mm_s: i16, w_mrad_s: i16 },
    Stop { reason: u8 },
    Estop,
    ClearFaults { mask: u16 },
    SetConfig { param_id: u8, value: [u8; 4] },
    /// Known or unknown type the firmware ignores (SET_LIMITS, short payloads, ...).
    Ignored { ty: u8 },
}

impl Command {
    /// Decode a parsed packet. Short payloads are ignored, as in `usb_rx.cpp`.
    pub fn decode(p: &Packet<'_>) -> Command {
        let d = p.data;
        match p.ty {
            cmd::SET_PROTOCOL_VERSION if !d.is_empty() => Command::SetProtocolVersion(d[0]),
            cmd::TIME_SYNC_REQ if d.len() >= 8 => {
                Command::TimeSyncReq { ping_seq: u32::from_le_bytes(d[0..4].try_into().unwrap()) }
            }
            cmd::SET_TWIST if d.len() >= 4 => Command::SetTwist {
                v_mm_s: i16::from_le_bytes([d[0], d[1]]),
                w_mrad_s: i16::from_le_bytes([d[2], d[3]]),
            },
            // The ESP32 treats STOP as a zero twist whatever the payload.
            cmd::STOP => Command::Stop { reason: d.first().copied().unwrap_or(0) },
            cmd::ESTOP => Command::Estop,
            cmd::CLEAR_FAULTS if d.len() >= 2 => Command::ClearFaults { mask: u16::from_le_bytes([d[0], d[1]]) },
            cmd::SET_CONFIG if d.len() >= 5 => {
                Command::SetConfig { param_id: d[0], value: [d[1], d[2], d[3], d[4]] }
            }
            ty => Command::Ignored { ty },
        }
    }

    /// Commands that update `cmd_seq_last_applied`'s source (`g_cmd_seq_last`): all but the
    /// common handshake / time-sync ones.
    pub fn is_reflex(&self) -> bool {
        !matches!(self, Command::SetProtocolVersion(_) | Command::TimeSyncReq { .. })
    }
}

// ---- Telemetry payloads (MCU -> host) ----

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
#[cfg_attr(feature = "defmt", derive(defmt::Format))]
pub struct State {
    pub speed_l_mm_s: i16,
    pub speed_r_mm_s: i16,
    pub gyro_z_mrad_s: i16,
    pub accel_x_mg: i16,
    pub accel_y_mg: i16,
    pub accel_z_mg: i16,
    pub fault_flags: u16,
    pub range_mm: u16,
    pub range_status: u8,
    /// v2 only.
    pub cmd_seq_last_applied: u32,
    /// v2 only.
    pub t_cmd_applied_us: u32,
}

impl State {
    pub const LEN_V1: usize = 17;
    pub const LEN_V2: usize = 25;

    /// Serialize; returns the payload length for `version`.
    pub fn write(&self, version: Version, out: &mut [u8; Self::LEN_V2]) -> usize {
        let fields: [i16; 6] = [
            self.speed_l_mm_s,
            self.speed_r_mm_s,
            self.gyro_z_mrad_s,
            self.accel_x_mg,
            self.accel_y_mg,
            self.accel_z_mg,
        ];
        for (i, f) in fields.iter().enumerate() {
            out[2 * i..2 * i + 2].copy_from_slice(&f.to_le_bytes());
        }
        out[12..14].copy_from_slice(&self.fault_flags.to_le_bytes());
        out[14..16].copy_from_slice(&self.range_mm.to_le_bytes());
        out[16] = self.range_status;
        match version {
            Version::V1 => Self::LEN_V1,
            Version::V2 => {
                out[17..21].copy_from_slice(&self.cmd_seq_last_applied.to_le_bytes());
                out[21..25].copy_from_slice(&self.t_cmd_applied_us.to_le_bytes());
                Self::LEN_V2
            }
        }
    }
}

/// BRINGUP_DIAG payload (13 bytes, `protocol.h::BringupDiagPayload`): raw encoder counts
/// during the open-loop motor test.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
#[cfg_attr(feature = "defmt", derive(defmt::Format))]
pub struct BringupDiag {
    /// 0 idle, 1 left fwd, 2 left rev, 3 right fwd, 4 right rev.
    pub phase: u8,
    /// 0 left, 1 right.
    pub side: u8,
    pub forward: bool,
    pub pwm_duty: u16,
    pub raw_l: i32,
    pub raw_r: i32,
}

impl BringupDiag {
    pub const LEN: usize = 13;

    pub fn write(&self) -> [u8; Self::LEN] {
        let mut b = [0u8; Self::LEN];
        b[0] = self.phase;
        b[1] = self.side;
        b[2] = self.forward as u8;
        b[3..5].copy_from_slice(&self.pwm_duty.to_le_bytes());
        b[5..9].copy_from_slice(&self.raw_l.to_le_bytes());
        b[9..13].copy_from_slice(&self.raw_r.to_le_bytes());
        b
    }
}

/// TIME_SYNC_RESP payload: `{ping_seq:u32, t_src_us:u64}`.
pub fn time_sync_resp(ping_seq: u32, t_src_us: u64) -> [u8; 12] {
    let mut b = [0u8; 12];
    b[0..4].copy_from_slice(&ping_seq.to_le_bytes());
    b[4..12].copy_from_slice(&t_src_us.to_le_bytes());
    b
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn crc_check_value() {
        // CRC-16/CCITT-FALSE check value.
        assert_eq!(crc16(b"123456789"), 0x29B1);
    }

    #[test]
    fn cobs_roundtrip_edges() {
        let cases: [&[u8]; 6] = [&[], &[0], &[0, 0], &[1, 2, 3], &[1, 0, 2, 0], &[0x11, 0x22, 0, 0x33]];
        for src in cases {
            let mut enc = [0u8; 16];
            let n = cobs_encode(src, &mut enc).unwrap();
            assert!(!enc[..n].contains(&0));
            let mut dec = [0u8; 16];
            let m = cobs_decode(&enc[..n], &mut dec).unwrap();
            assert_eq!(&dec[..m], src);
        }
        // 254 and 255 non-zero bytes: block boundaries.
        for len in [253usize, 254, 255, 300] {
            let src: std::vec::Vec<u8> = (0..len).map(|i| (i % 255 + 1) as u8).collect();
            let mut enc = [0u8; 400];
            let n = cobs_encode(&src, &mut enc).unwrap();
            let mut dec = [0u8; 400];
            let m = cobs_decode(&enc[..n], &mut dec).unwrap();
            assert_eq!(&dec[..m], &src[..], "len {len}");
        }
    }

    #[test]
    fn cobs_rejects_bad_input() {
        let mut d = [0u8; 8];
        assert_eq!(cobs_decode(&[0x03, 0x01], &mut d), None); // truncated
        assert_eq!(cobs_decode(&[0x01, 0x00], &mut d), None); // zero where a code byte belongs
        assert_eq!(cobs_decode(&[0x09, 1, 2, 3, 4, 5, 6, 7, 8], &mut [0u8; 4]), None); // overflow
    }

    #[test]
    fn build_parse_roundtrip_both_versions() {
        for v in [Version::V1, Version::V2] {
            let mut frame = [0u8; 64];
            let n = build(v, cmd::SET_TWIST, 0x1234_5678, 42, &[1, 0, 0xFF, 0xFF], &mut frame).unwrap();
            assert_eq!(frame[n - 1], 0);
            let mut buf = [0u8; 64];
            let p = parse(v, &frame[..n - 1], &mut buf).unwrap();
            assert_eq!(p.ty, cmd::SET_TWIST);
            match v {
                Version::V1 => assert_eq!((p.seq, p.t_src_us), (0x78, 0)),
                Version::V2 => assert_eq!((p.seq, p.t_src_us), (0x1234_5678, 42)),
            }
            assert_eq!(Command::decode(&p), Command::SetTwist { v_mm_s: 1, w_mrad_s: -1 });
        }
    }

    #[test]
    fn parse_rejects_bad_crc() {
        let mut frame = [0u8; 64];
        let n = build(Version::V1, cmd::ESTOP, 1, 0, &[], &mut frame).unwrap();
        let mut raw = [0u8; 64];
        let m = cobs_decode(&frame[..n - 1], &mut raw).unwrap();
        raw[m - 1] ^= 1;
        let mut enc = [0u8; 64];
        let k = cobs_encode(&raw[..m], &mut enc).unwrap();
        assert!(parse(Version::V1, &enc[..k], &mut [0u8; 64]).is_none());
    }

    #[test]
    fn accumulator_splits_and_discards_overlong() {
        let mut acc = FrameAccumulator::new();
        let mut frames = std::vec::Vec::new();
        let mut stream = std::vec![0u8, 5, 6, 0];
        stream.extend(core::iter::repeat_n(7u8, MAX_RX_FRAME + 5));
        stream.extend([0, 8, 9, 0]);
        for b in stream {
            if let Some(f) = acc.push(b) {
                frames.push(f.to_vec());
            }
        }
        assert_eq!(frames, std::vec![std::vec![5, 6], std::vec![8, 9]]);
    }

    #[test]
    fn state_layout() {
        let s = State {
            speed_l_mm_s: -2,
            fault_flags: fault::ESTOP | fault::OBSTACLE,
            range_mm: 300,
            range_status: range_status::OK,
            cmd_seq_last_applied: 7,
            t_cmd_applied_us: 9,
            ..Default::default()
        };
        let mut b = [0u8; State::LEN_V2];
        assert_eq!(s.write(Version::V1, &mut b), 17);
        assert_eq!(&b[0..2], &[0xFE, 0xFF]);
        assert_eq!(&b[12..14], &[0x42, 0x00]);
        assert_eq!(s.write(Version::V2, &mut b), 25);
        assert_eq!(&b[17..25], &[7, 0, 0, 0, 9, 0, 0, 0]);
    }
}
