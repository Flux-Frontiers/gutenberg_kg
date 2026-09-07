# Bundle specs

Hand-written TOML files, each naming a subset of the corpus to ship as a
named, versioned bundle: a genre or a list of books, a diary policy, and the
golden queries the exported pack must answer correctly.

This is the one directory under `bundles/` that is committed. Everything
else there is build output — multi-gigabyte and fully reproducible from the
corpus — and stays ignored.

```sh
gutenkg bundle validate bundles/specs/<name>.toml
gutenkg bundle resolve bundles/specs/<name>.toml
```

See `analysis/SELECTIVE_BUNDLE_EXPORT_PLAN.md` for the spec format and the
resolution rules. Example specs land in phase 5 of that plan; there are none
committed yet.
