//! Host link session: what `esp32-reflex/main/usb_rx.cpp` + `telemetry.cpp` do around the wire
//! format. Owns the negotiated protocol version, the TX sequence and the last applied command
//! sequence; answers SET_PROTOCOL_VERSION and TIME_SYNC_REQ itself and hands reflex commands
//! to the caller. Transport-agnostic: feed it bytes, give it a sink for frames.

use crate::protocol::{self, Command, FrameAccumulator, State, Version, tel};

/// Largest frame the link emits (STATE v2: 13 + 25 + 2 bytes, COBS + delimiter).
pub const MAX_TX_FRAME: usize = 64;

pub struct Link {
    acc: FrameAccumulator,
    version: Version,
    tx_seq: u32,
    /// Seq of the last reflex command received (`g_cmd_seq_last`).
    pub cmd_seq_last: u32,
    pub rx_ok: u32,
    pub rx_bad: u32,
}

impl Default for Link {
    fn default() -> Self {
        Self::new()
    }
}

impl Link {
    pub const fn new() -> Self {
        Self { acc: FrameAccumulator::new(), version: Version::V1, tx_seq: 0, cmd_seq_last: 0, rx_ok: 0, rx_bad: 0 }
    }

    pub fn version(&self) -> Version {
        self.version
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
            let Some(pkt) = protocol::parse(self.version, frame, &mut buf) else {
                self.rx_bad += 1;
                continue;
            };
            self.rx_ok += 1;
            let c = Command::decode(&pkt);
            match c {
                Command::SetProtocolVersion(v @ (1 | 2)) => {
                    self.version = if v == 2 { Version::V2 } else { Version::V1 };
                    let mut out = [0u8; MAX_TX_FRAME];
                    if let Some(n) = self.build(tel::PROTOCOL_VERSION_ACK, now_us, &[v], &mut out) {
                        send(&out[..n]);
                    }
                }
                Command::SetProtocolVersion(_) => {}
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

    /// Build a STATE frame in the negotiated version.
    pub fn state_frame(&mut self, s: &State, now_us: u64, out: &mut [u8; MAX_TX_FRAME]) -> Option<usize> {
        let mut payload = [0u8; State::LEN_V2];
        let n = s.write(self.version, &mut payload);
        self.build(tel::STATE, now_us, &payload[..n], out)
    }

    fn build(&mut self, ty: u8, now_us: u64, data: &[u8], out: &mut [u8]) -> Option<usize> {
        let seq = self.tx_seq;
        self.tx_seq = self.tx_seq.wrapping_add(1);
        protocol::build(self.version, ty, seq, now_us, data, out)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::protocol::{build, cmd, parse};
    use std::vec::Vec;

    fn frame(v: Version, ty: u8, seq: u32, data: &[u8]) -> Vec<u8> {
        let mut out = [0u8; 64];
        let n = build(v, ty, seq, 0, data, &mut out).unwrap();
        out[..n].to_vec()
    }

    #[test]
    fn handshake_then_v2_commands_and_time_sync() {
        let mut link = Link::new();
        let mut sent: Vec<Vec<u8>> = Vec::new();
        let mut cmds = Vec::new();

        // Supervisor sends the handshake in a v1 envelope (serial_transport.negotiate_v2).
        let hs = frame(Version::V1, cmd::SET_PROTOCOL_VERSION, 0, &[2]);
        link.feed(&hs, 1000, |f| sent.push(f.to_vec()), |c, s| cmds.push((c, s)));
        assert_eq!(link.version(), Version::V2);
        let mut buf = [0u8; 128];
        let ack = parse(Version::V2, &sent[0][..sent[0].len() - 1], &mut buf).unwrap();
        assert_eq!((ack.ty, ack.data, ack.t_src_us), (tel::PROTOCOL_VERSION_ACK, &[2u8][..], 1000));

        // Time sync and a twist, back to back in one read.
        let mut bytes = frame(Version::V2, cmd::TIME_SYNC_REQ, 10, &[77, 0, 0, 0, 0, 0, 0, 0]);
        bytes.extend(frame(Version::V2, cmd::SET_TWIST, 0x0001_0000, &[100, 0, 0, 0]));
        link.feed(&bytes, 5_000_000_000, |f| sent.push(f.to_vec()), |c, s| cmds.push((c, s)));
        let ts = parse(Version::V2, &sent[1][..sent[1].len() - 1], &mut buf).unwrap();
        assert_eq!(ts.ty, tel::TIME_SYNC_RESP);
        assert_eq!(ts.data, &protocol::time_sync_resp(77, 5_000_000_000)[..]);
        assert_eq!(cmds, [(Command::SetTwist { v_mm_s: 100, w_mrad_s: 0 }, 0x0001_0000)]);
        assert_eq!(link.cmd_seq_last, 0x0001_0000);
        // Time sync is a common command: it does not move cmd_seq_last.
        assert_eq!(link.rx_ok, 3);
    }

    #[test]
    fn host_restart_falls_back_to_v1_handshake() {
        let mut link = Link::new();
        let hs2 = frame(Version::V1, cmd::SET_PROTOCOL_VERSION, 0, &[2]);
        link.feed(&hs2, 0, |_| {}, |_, _| {});
        // A restarted supervisor is at v1 again and re-sends the v1 handshake: still understood.
        let mut acks = 0;
        link.feed(&hs2, 0, |_| acks += 1, |_, _| {});
        assert_eq!((acks, link.version()), (1, Version::V2));
        // ReflexClient keeps sending v1-envelope commands after v2 is negotiated: they decode
        // to < 15 bytes, so parse() falls back to v1, as on the ESP32.
        let mut got = Vec::new();
        link.feed(&frame(Version::V1, cmd::SET_TWIST, 9, &[1, 0, 2, 0]), 0, |_| {}, |c, s| got.push((c, s)));
        assert_eq!(got, [(Command::SetTwist { v_mm_s: 1, w_mrad_s: 2 }, 9)]);
        let hs1 = frame(Version::V1, cmd::SET_PROTOCOL_VERSION, 0, &[1]);
        link.feed(&hs1, 0, |_| {}, |_, _| {});
        assert_eq!(link.version(), Version::V1);
    }

    #[test]
    fn garbage_counts_as_bad_and_resyncs() {
        let mut link = Link::new();
        let mut bytes = std::vec![0x05, 0x99, 0x00];
        bytes.extend(frame(Version::V1, cmd::ESTOP, 3, &[]));
        let mut got = Vec::new();
        link.feed(&bytes, 0, |_| {}, |c, _| got.push(c));
        assert_eq!(link.rx_bad, 1);
        assert_eq!(got, [Command::Estop]);
    }

    #[test]
    fn state_frame_follows_version() {
        let mut link = Link::new();
        let mut out = [0u8; MAX_TX_FRAME];
        let s = State { range_mm: 287, ..Default::default() };
        let n1 = link.state_frame(&s, 9, &mut out).unwrap();
        let mut buf = [0u8; 128];
        assert_eq!(parse(Version::V1, &out[..n1 - 1], &mut buf).unwrap().data.len(), State::LEN_V1);
        link.feed(&frame(Version::V1, cmd::SET_PROTOCOL_VERSION, 0, &[2]), 0, |_| {}, |_, _| {});
        let n2 = link.state_frame(&s, 9, &mut out).unwrap();
        let p = parse(Version::V2, &out[..n2 - 1], &mut buf).unwrap();
        assert_eq!((p.data.len(), p.t_src_us), (State::LEN_V2, 9));
    }
}
