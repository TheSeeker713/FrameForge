# Devlog

## 2026-10-07 — Library studio

A local WebGL studio at `design/library-studio` lets the Library look be chosen before any app code changes. Choices, kept looks, discarded looks, and notes write themselves to `docs/LIBRARY_DESIGN_FEEDBACK.md`. Reopening the page restores the in-progress answers. The room is a draped wall and walnut floor; cards use brushed metal, paper fiber, or glass edges around a composed still.

## 2026-10-07 — v0.6.19

The Close to system tray switch did not hide the window. The minimize button now does that, and the download keeps running. The tray icon can reopen the window, pause or resume, start pending downloads, and import a URL list or completed downloads.

## 2026-10-07 — v0.6.18

The app was still creating `%USERPROFILE%\Downloads\FrameForge` (database, cookies, models, thumbnails, temp) after a custom folder had been chosen. That tree is now created only when onboarding explicitly uses the Windows default. A custom pick stores the whole app under `<picked>\FrameForge`.

## 2026-10-07 — v0.6.17

Library rows show thumbnails and play inside the app. Queue and History still open the Windows player. The Flet geolocator plugin is replaced with a no-op so Windows location is not started; coordinates are not read or sent anywhere. When cookies for a failing site are already validated, the queue retries and resumes without the pause dialog.
