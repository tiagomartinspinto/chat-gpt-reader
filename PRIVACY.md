# Privacy and Safety

This reader is designed for local use with private ChatGPT exports. Treat generated indexes as private data.

## Private Files

These files and folders can contain private data:

- `exports/`
- `data/search-index.json`
- loose ZIP, PDF, JSON, JSONL, transcript, screenshot, and backup files
- any extracted folder that contains `conversations.json`

## Git Ignores

The repository ignores common private export material, including `exports/`, `data/*.json`, `*.zip`, `*.pdf`, `conversations.json`, backups, and local environment files. Keep synthetic fixtures in version control only when they contain no real chat content.

## Clean Generated Data

To remove local generated data, delete `data/search-index.json` and remove any private files from `exports/` or other local import folders. Deleting `exports/` alone is not enough if `data/search-index.json` remains.

The reader can fall back to `demo/search-index.json` after private generated data is removed.

## If Private Data Was Committed

Stop pushing or sharing the repository, remove the private files from the branch, and rewrite the repository history with a tool such as `git filter-repo` or BFG Repo-Cleaner. After force-pushing the cleaned history, rotate any exposed credentials or secrets, ask collaborators to delete old clones, and contact the hosting provider if cached private blobs need removal.
