# Adaptive Realtime Mode

Version 0.2.0 prioritizes staying close to live time over image quality.

## What is measured

The viewer samples approximately every 1.5 seconds:

- Total Windows CPU utilization.
- Total RAM utilization and application resident memory.
- Current receive throughput and reported NIC link speed.
- Per-camera bytes received, displayed frames and lost frames from LibVLC media statistics.
- RTSP discontinuities, corrupted packets and rebuffering events.
- Short-window variation in bitrate and displayed FPS as an estimated jitter signal.

The jitter value is an estimate. Direct RTP inter-arrival jitter is not exposed by the current embedded LibVLC pipeline.

## Adaptation order

The controller uses this order:

1. Drop frames that are already late instead of allowing latency to accumulate.
2. Keep hidden cameras stopped.
3. Use the configured Grid/substream URL in multi-camera layouts.
4. Force an unstable camera to its Grid/substream URL even in 1x1 or fullscreen.
5. Adjust RTSP cache within the configured realtime range.
6. Show a small warning above the application title when resources or streams remain unhealthy.

The controller uses consecutive bad samples, a minimum switch interval and a longer recovery window. This prevents repeated main/substream switching caused by short CPU or network spikes.

## Important limitation

The viewer does not transcode video and does not change camera encoder settings. Therefore it cannot invent a lower resolution or lower FPS stream.

For automatic quality reduction, each camera must expose a low-bandwidth RTSP profile and it must be entered as **Grid/substream URL** in Camera Settings.

Recommended low-bandwidth profile:

- Codec: H.264
- Resolution: 640x360, 704x576, or 720p
- FPS: 10-20
- Bitrate: 400-1500 Kbps
- GOP: 1-2 seconds

## Default settings

```json
{
  "adaptive_realtime": true,
  "adaptive_sample_interval_ms": 1500,
  "adaptive_cpu_high_percent": 78,
  "adaptive_cpu_critical_percent": 92,
  "adaptive_memory_high_percent": 86,
  "adaptive_min_switch_seconds": 12,
  "adaptive_recovery_samples": 8,
  "adaptive_bad_samples_before_switch": 3,
  "adaptive_cache_min_ms": 100,
  "adaptive_cache_max_ms": 350
}
```

Older camera configuration files remain compatible. Missing settings use these defaults and are written into the JSON the next time the application saves configuration.
