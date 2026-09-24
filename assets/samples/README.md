# Built-in sample video

`white-dot-loop.mp4` is derived from the video selected in the user's OBS media
source: `white-dot-02s-16s.mp4` (the 2–16 second segment of the supplied recording).

- Same 14-second segment, looped at its original playback speed.
- Black detection area only: crop `(0, 1080, 1920, 1080)` from the 1920×2160 source.
- Native 1920×1080 pixel dimensions preserved; 120 fps sampled to 30 fps.
- MP4 video, no audio. No OBS installation or source selection needed for playback.
- Preview only: does not start monitoring, recording or warning sounds.
- Each loop starts a new coordinate reference to avoid a false end-to-start delta.

Included as the demonstration clip at the repository owner's request.
