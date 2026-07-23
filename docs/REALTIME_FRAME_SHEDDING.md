# Realtime Frame Shedding

Version 0.2.1 adds decoder-level frame shedding for PCs that cannot keep up with every camera frame.

## Why this is different from drawing one frame per second

Discarding frames only after they have already been received and decoded does not reduce RTSP bandwidth or decoder work. LAN Camera Viewer instead asks VLC/libavcodec to discard selected frames inside the decoder.

The policy uses the same discard levels exposed by VLC's `avcodec-skip-frame` option:

- `0`: normal decoding;
- `1`: discard non-reference frames;
- `2`: discard bidirectional frames under critical pressure;
- `3`: emergency keyframe-only rescue.

## Policy

- Healthy single-camera/main-stream playback uses level 0.
- Grid/substream playback uses level 1 to reduce decode load.
- Critical CPU pressure uses level 2.
- If RTSP data continues arriving but no new picture is displayed for three telemetry samples, the affected camera temporarily enters level 3 for 45 seconds.
- If neither data nor pictures arrive, the stale RTSP pipeline is restarted instead of pretending that frame dropping can solve a network stall.
- A 15-second restart cooldown prevents reconnect loops.

VLC late-frame dropping is enabled globally so the decoder can abandon stale work and catch up to current time.

## Important limitations

Frame shedding reduces CPU/GPU decoder work, but it does not reduce camera-side bitrate. To reduce bandwidth, configure a real camera substream with lower resolution, FPS, and bitrate.

Keyframe-only rescue updates at the camera GOP interval, not at an exact one frame per second. Configure the camera GOP/keyframe interval to about one second for a useful emergency view.

RTSP over TCP may still freeze during retransmission on a poor network. Frame shedding cannot recover packets that have not arrived; the watchdog reconnects a pipeline that stops receiving data.
