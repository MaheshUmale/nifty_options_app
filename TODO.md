## Upstox SDK removal - TODO

- [ ] Rewrite `src/data/upstox_client.py` to remove ALL `upstox_client` SDK imports/calls.
  - [ ] Implement OAuth token exchange via direct HTTP call.
  - [ ] Implement market quote LTP via direct REST HTTP call.
  - [ ] Implement option chain via direct REST HTTP call.
  - [ ] Keep instrument master download/caching + `resolve_option_instrument_master(...)` logic intact.

- [ ] Rewrite `src/data/streaming.py` to remove SDK websocket (`MarketDataStreamerV3`) usage.
  - [ ] Switch `UpstoxStreamer` to polling-only using the new REST client.
  - [ ] Ensure existing consumers of `UpstoxStreamer.subscribe/connect` still work.

- [ ] Remove/adjust any other imports referencing SDK types (if tests fail).
  - [ ] `scripts/upstox_auth_helper.py` import correctness (ensure token exchange works).

- [ ] Run tests (e.g., `pytest`) to confirm the last failure is resolved.
