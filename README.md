# lp2-video

Did you know LP2 recordings on minidiscs have some empty padding space? Did you also know 7-8 of these bytes are (almost) completely ignored by decoders?

Soooo, here is some insanity that allowed me to have a 10FPS 32x24 monochorme video crammed inside its own audio data; with it being still playable on all my MDLP (NE410, N510, MT80, MT280) players!

### Known Drawbacks

 - Currently I only tested with Bad Apple, what else would I use; but in theory any such tiny video should be encodable.
 - Unless you write this bit perfect and read the disc bit-perfect there will be glitches in both the video and audio sadly.

### Can the video be played back on an actual MD player?

In theory, yes. If it has an at least 32x24 screen (or you tweak the resolution) and can read arbitrary bytes without distrupting playback, it should be possible. I haven't tried firmware-hacking any players.

### What's the point then?

Tbh, I was just curious if it was possible.

### Why 10.775862069 FPS?

Because this way a frame is exactly 8 sound groups (`1000 / (11.6*8) = 10.775...`).
