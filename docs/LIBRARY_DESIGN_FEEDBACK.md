# Library module — design answers

This file is overwritten by the library studio while it is open.
Read it before planning the Library build. The videos stay where they already are; this session only chooses how the Library looks and behaves.

Status: in progress
Updated: 2026-10-08T02:27:19.604Z
Renderer: WebGL2 · Three r0.186.1 · WebGL2
Frames per second (latest sample): 100

## Chosen layers

- Shelf: Cover flow
- Card: Optical glass
- Pointer: Magnetic pull
- Open: Card comes forward
- Anamorphic streak: On
- Floor mirror: On
- Film grain: Off
- Vignette: On

## Manual shelf order

1. Interview clip
2. Recital
3. Lecture excerpt
4. Demo recording
5. Field note
6. Trailer cut
7. News segment

## Looks kept

None yet.

## Looks discarded

None yet.

## Notes

> I want a more polish professional yet epic looking graphics, animation, and interactions. This is a good step forward, but I to see if you can push further into aweinspiring graphics, textures that make this video player/ video library even more better.
> 
> There should be features like what you presented before, but with this and better graphics, better animations, and a more improved design layout for showcasing video thumbnails, and playing videos. we should have files sorting options, editing options, delete or move clips into albums, albums, are a database, files will remain from source location, albums will be a visual and interactive ux/ui for organizing video clips.
> 
> this is a library, so we should have a design mechanic in mind. feel free to ask me questions... feel free to offer suggestions... do not implement anything

## Recent changes

- 2026-10-08T02:26:55.659Z: Notes updated
- 2026-10-08T02:26:55.907Z: Notes updated
- 2026-10-08T02:26:56.050Z: Notes updated
- 2026-10-08T02:26:56.185Z: Notes updated
- 2026-10-08T02:26:56.315Z: Notes updated
- 2026-10-08T02:26:56.575Z: Notes updated
- 2026-10-08T02:26:56.739Z: Notes updated
- 2026-10-08T02:26:56.811Z: Notes updated
- 2026-10-08T02:26:57.649Z: Notes updated
- 2026-10-08T02:26:57.782Z: Notes updated
- 2026-10-08T02:27:00.975Z: Notes updated
- 2026-10-08T02:27:01.249Z: Notes updated
- 2026-10-08T02:27:01.468Z: Notes updated
- 2026-10-08T02:27:01.951Z: Notes updated
- 2026-10-08T02:27:07.557Z: Notes updated
- 2026-10-08T02:27:07.755Z: Notes updated
- 2026-10-08T02:27:08.129Z: Notes updated
- 2026-10-08T02:27:08.421Z: Notes updated
- 2026-10-08T02:27:08.525Z: Notes updated
- 2026-10-08T02:27:09.347Z: Notes updated
- 2026-10-08T02:27:09.529Z: Notes updated
- 2026-10-08T02:27:09.809Z: Notes updated
- 2026-10-08T02:27:09.941Z: Notes updated
- 2026-10-08T02:27:10.227Z: Notes updated
- 2026-10-08T02:27:10.335Z: Notes updated
- 2026-10-08T02:27:10.577Z: Notes updated
- 2026-10-08T02:27:10.855Z: Notes updated
- 2026-10-08T02:27:11.022Z: Notes updated
- 2026-10-08T02:27:11.161Z: Notes updated
- 2026-10-08T02:27:11.359Z: Notes updated
- 2026-10-08T02:27:11.699Z: Notes updated
- 2026-10-08T02:27:11.917Z: Notes updated
- 2026-10-08T02:27:12.058Z: Notes updated
- 2026-10-08T02:27:12.527Z: Notes updated
- 2026-10-08T02:27:12.695Z: Notes updated
- 2026-10-08T02:27:12.835Z: Notes updated
- 2026-10-08T02:27:13.157Z: Notes updated
- 2026-10-08T02:27:13.215Z: Notes updated
- 2026-10-08T02:27:13.348Z: Notes updated
- 2026-10-08T02:27:19.397Z: Notes updated

## Research this session is built from

- Three.js 0.186 WebGPURenderer and TSL post-processing (anamorphic bloom, SSR). The studio uses the WebGL2 renderer so the Radeon 680M can run it, and draws the anamorphic streak as its own pass.
- MeshPhysicalMaterial transmission, thickness, IOR, dispersion, and iridescence. Drei's MeshTransmissionMaterial (Codrops, March 2025) re-renders the scene per glass object; the built-in physical material shares one transmission pass.
- A planar floor reflector, not screen-space reflections. SSR is the heavier WebGPU demo.
- Infuse list-versus-poster threads (September 2025): long file names need a shelf, and a poster grid is a second view.
- Jellyfin: removing a library does not delete the folder. There is still no first-class 'remove this title and keep the file' action, which is the gap FrameForge should close.
