# Original workstream history

`tech-europe-workstreams.bundle` contains complete Git histories for the all ten original Tech Europe branches. The final Resilix web application's own history is preserved directly in this fork's ancestry.

```sh
git bundle verify history/tech-europe-workstreams.bundle
git clone history/tech-europe-workstreams.bundle recovered-workstreams
git -C recovered-workstreams switch --detach 904997023bd5b3bc8b9a628dee14ab34ff50fd8b
```

Source folders are snapshots of the commits in `SOURCES.json`; documentation edits are recorded in the consolidation commit. Original repositories remain unchanged.
