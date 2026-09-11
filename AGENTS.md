# Publishing

Update the manifest version and `CHANGELOG.md`, commit, and push `main`.
Once CI passes, publish a stable GitHub release `vX.Y.Z` at that commit, matching the manifest version; include any migration notes.
HACS reads GitHub releases directly. No ZIP upload is needed.
