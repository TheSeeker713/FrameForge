# Hardware notes

**Target machine:** Windows 11 Pro, AMD Ryzen 7 6800H, Radeon 680M iGPU, 32 GB RAM.

## Acceleration preference

1. **DirectML** via `onnxruntime-directml` (`DmlExecutionProvider`)
2. **CPU** (`CPUExecutionProvider`) if DirectML unavailable
3. Vulkan tooling may be present on the system (`vulkaninfo`); FrameForge v1 inference path is ONNX DirectML/CPU, not a separate Vulkan upscaler stack

## Practical tips

- Keep tile sizes modest on 680M to avoid VRAM pressure
- Sequential downloads reduce sustained disk/network contention during upscale
- Store models and temp frames under `%USERPROFILE%\Downloads\FrameForge\` (typically on the user profile volume)
