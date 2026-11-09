# modpoll-wot repository conventions

- Review the working tree and current branch before editing. Integrate changes into `main` through a reviewed pull request with passing CI.
- This repository owns the shared TM/TD executable profile, its bundled schemas, and the offline CLI. Modpoll, Modsim, Open Modbus Catalog, and ModioHub consume published releases only.
- Run `mise run check` before opening a pull request.
- Released versions and tags are immutable. Release the producer first, then update consumer pins in their own repositories. See [README](README.md#releases).
- Keep the package free of Modbus execution, schedulers, network services, and device metadata records.
- Use English and lowercase kebab-case filenames except where an external tool requires a different name.
