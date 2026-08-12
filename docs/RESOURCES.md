# Resource monitor

While an **upscale** is active, FrameForge samples CPU and RAM with **psutil** about once per second.

## Defaults

| Setting | Default |
|---------|---------|
| Enable monitor | on |
| RAM warning | 90% |
| CPU warning | 95% |
| Sustained seconds | 8 |
| Auto-pause on critical RAM | off |

Warnings require the threshold to hold for the sustained window (not a single spike). A non-blocking banner appears in the main window.

If **Auto-pause upscale on sustained RAM pressure** is enabled, the upscale job is paused with reason `resource_pressure`. Resume still works (returns to the upscale chain). Monitoring failures are non-fatal.

GPU / iGPU VRAM is not required for this pass.

Configure under **Settings**.
