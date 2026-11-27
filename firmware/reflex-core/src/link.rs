//! Host link session: what `esp32-reflex/main/usb_rx.cpp` + `telemetry.cpp` do around the wire
//! format, **v2 only** (PROTOCOL.md 3.2, amended 2026-11-27): every frame out is v2 from boot,
//! and the one v1-envelope frame accepted is the SET_PROTOCOL_VERSION handshake request, which
//! is always ACKed with version 2 in a v2 envelope. An MCU reset therefore cannot desync the
//! envelope. Answers the handshake and TIME_SYNC_REQ itself and hands reflex commands to the
//! caller. Transport-agnostic: feed it bytes, give it a sink for frames.

use crate::protocol::{self, Command, FrameAccumulator, State, Version, tel};

/// Largest frame the link emits (STATE v2: 13 + 25 + 2 bytes, COBS + delimiter).
pub const MAX_TX_FRAME: usize = 64;

pub struct Link {
    acc: FrameAccumulator,
    tx_seq: u32,
    /// Seq of the last reflex command received (`g_cmd_seq_last`).
    pub cmd_seq_last: u32,
    pub rx_ok: u32,
    /// CRC / COBS failures.
    pub rx_bad: u32,
    /// Valid v1-envelope frames other than the handshake (a host that skipped the handshake).
    pub rx_v1_dropped: u32,
}

impl Default for Link {
    fn default() -> Self {
        Self::new()
    }
}

impl Link {
    pub const fn new() -> Self {
        Self { acc: FrameAccumulator::new(), tx_seq: 0, cmd_seq_last: 0, rx_ok: 0, rx_bad: 0, rx_v1_dropped: 0 }
    }

    /// Feed received bytes. Replies to the common commands go to `send`; reflex commands go to
    /// `on_cmd` with their packet seq.
    pub fn feed(
        &mut self,
        bytes: &[u8],
        now_us: u64,
        mut send: impl FnMut(&[u8]),
        mut on_cmd: impl FnMut(Command, u32),
    ) {
        for &b in bytes {
            let Some(frame) = self.acc.push(b) else { continue };
            let mut buf = [0u8; protocol::MAX_RX_FRAME];
            // parse() at V2 falls back to the v1 layout for frames shorter than a v2 header.
            let Some(pkt) = protocol::parse(Version::V2, frame, &mut buf) else {
                self.rx_bad += 1;
                continue;
            };
            let v1_envelope = is_v1(frame);
            let c = Command::decode(&pkt);
            if let Command::SetProtocolVersion(_) = c {
                self.rx_ok += 1;
                let mut out = [0u8; MAX_TX_FRAME];
                if let Some(n) = self.build(tel::PROTOCOL_VERSION_ACK, now_us, &[2], &mut out) {
                    send(&out[..n]);
                }
                continue;
            }
            if v1_envelope {
                self.rx_v1_dropped += 1;
                continue;
            }
            self.rx_ok += 1;
            match c {
                Command::TimeSyncReq { ping_seq } => {
                    let mut out = [0u8; MAX_TX_FRAME];
                    let resp = protocol::time_sync_resp(ping_seq, now_us);
                    if let Some(n) = self.build(tel::TIME_SYNC_RESP, now_us, &resp, &mut out) {
                        send(&out[..n]);
                    }
                }
                c => {
                    self.cmd_seq_last = pkt.seq;
                    on_cmd(c, pkt.seq);
                }
            }
        }
    }

    /// Build a STATE frame (v2, 25-byte payload).
    pub fn state_frame(&mut self, s: &State, now_us: u64, out: &mut [u8; MAX_TX_FRAME]) -> Option<usize> {
        let mut payload = [0u8; State::LEN_V2];
        let n = s.write(Version::V2, &mut payload);
        self.build(tel::STATE, now_us, &payload[..n], out)
    }

    /// Build a BRINGUP_DIAG frame (v2).
    pub fn bringup_frame(
        &mut self,
        d: &protocol::BringupDiag,
        now_us: u64,
        out: &mut [u8; MAX_TX_FRAME],
    ) -> Option<usize> {
        self.build(tel::BRINGUP_DIAG, now_us, &d.write(), out)
    }

    fn build(&mut self, ty: u8, now_us: u64, data: &[u8], out: &mut [u8]) -> Option<usize> {
        let seq = self.tx_seq;
        self.tx_seq = self.tx_seq.wrapping_add(1);
        protocol::build(Version::V2, ty, seq, now_us, data, out)
    }
}

/// True when a valid frame decodes shorter than a v2 header + CRC, i.e. it is a v1 envelope.
fn is_v1(frame: &[u8]) -> bool {
    let mut buf = [0u8; protocol::MAX_RX_FRAME];
    protocol::cobs_decode(frame, &mut buf).is_some_and(|n| n < protocol::V2_HEADER + 2)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::protocol::{build, cmd, parse};
    use std::vec::Vec;

    fn frame(v: Version, ty: u8, seq: u32, data: &[u8]) -> Vec<u8> {
        let mut out = [0u8; 64];
        let n = build(v, ty, seq, 7, data, &mut out).unwrap();
        out[..n].to_vec()
    }

    fn parse_v2(f: &[u8]) -> (u8, u32, u64, Vec<u8>) {
        let mut buf = [0u8; 128];
        let p = parse(Version::V2, &f[..f.len() - 1], &mut buf).unwrap();
        (p.ty, p.seq, p.t_src_us, p.data.to_vec())
    }

    #[test]
    fn v1_handshake_acked_in_v2() {
        let mut link = Link::new();
        let mut sent: Vec<Vec<u8>> = Vec::new();
        link.feed(&frame(Version::V1, cmd::SET_PROTOCOL_VERSION, 0, &[2]), 1000, |f| sent.push(f.to_vec()), |_, _| {});
        assert_eq!(parse_v2(&sent[0]), (tel::PROTOCOL_VERSION_ACK, 0, 1000, std::vec![2]));
        // A request for v1 still gets "2": this firmware has no v1.
        link.feed(&frame(Version::V1, cmd::SET_PROTOCOL_VERSION, 1, &[1]), 0, |f| sent.push(f.to_vec()), |_, _| {});
        assert_eq!(parse_v2(&sent[1]).3, std::vec![2]);
    }

    #[test]
    fn v2_commands_and_time_sync() {
        let mut link = Link::new();
        let mut sent: Vec<Vec<u8>> = Vec::new();
        let mut cmds = Vec::new();
        let mut bytes = frame(Version::V2, cmd::TIME_SYNC_REQ, 10, &[77, 0, 0, 0, 0, 0, 0, 0]);
        bytes.extend(frame(Version::V2, cmd::SET_TWIST, 0x0001_0000, &[100, 0, 0, 0]));
        link.feed(&bytes, 5_000_000_000, |f| sent.push(f.to_vec()), |c, s| cmds.push((c, s)));
        let ts = parse_v2(&sent[0]);
        assert_eq!((ts.0, ts.3), (tel::TIME_SYNC_RESP, protocol::time_sync_resp(77, 5_000_000_000).to_vec()));
        assert_eq!(cmds, [(Command::SetTwist { v_mm_s: 100, w_mrad_s: 0 }, 0x0001_0000)]);
        assert_eq!(link.cmd_seq_last, 0x0001_0000);
        // ESTOP is the shortest command: 13 + 0 + 2 = 15 bytes, still v2.
        link.feed(&frame(Version::V2, cmd::ESTOP, 11, &[]), 0, |_| {}, |c, s| cmds.push((c, s)));
        assert_eq!(cmds[1], (Command::Estop, 11));
    }

    #[test]
    fn v1_commands_dropped() {
        let mut link = Link::new();
        let mut got = Vec::new();
        link.feed(&frame(Version::V1, cmd::SET_TWIST, 9, &[1, 0, 2, 0]), 0, |_| {}, |c, _| got.push(c));
        link.feed(&frame(Version::V1, cmd::ESTOP, 3, &[]), 0, |_| {}, |c, _| got.push(c));
        assert!(got.is_empty());
        assert_eq!((link.rx_v1_dropped, link.cmd_seq_last), (2, 0));
    }

    #[test]
    fn garbage_counts_as_bad_and_resyncs() {
        let mut link = Link::new();
        let mut bytes = std::vec![0x05, 0x99, 0x00];
        bytes.extend(frame(Version::V2, cmd::ESTOP, 3, &[]));
        let mut got = Vec::new();
        link.feed(&bytes, 0, |_| {}, |c, _| got.push(c));
        assert_eq!(link.rx_bad, 1);
        assert_eq!(got, [Command::Estop]);
    }

    #[test]
    fn state_frame_is_v2() {
        let mut link = Link::new();
        let mut out = [0u8; MAX_TX_FRAME];
        let s = State { range_mm: 287, cmd_seq_last_applied: 5, ..Default::default() };
        let n = link.state_frame(&s, 9, &mut out).unwrap();
        let p = parse_v2(&out[..n]);
        assert_eq!((p.0, p.2, p.3.len()), (tel::STATE, 9, State::LEN_V2));
    }
}
