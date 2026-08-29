# GUI tests

- Use `pytest-qt`; never start a nested Qt event loop manually.
- CI and local automation use `QT_QPA_PLATFORM=offscreen`.
- Prefer injected application services or runtime-generated media; do not commit video fixtures.
- Test widget behavior and state synchronization, not pixel-perfect platform rendering.
