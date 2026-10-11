The profile's Open-source work table is refreshed by GitHub Actions at 01:17 and
13:17 UTC (09:17 and 21:17 in China). Run **Update open-source work** from the
Actions tab for an immediate refresh. Scheduled runs can be delayed by GitHub.

The updater discovers public pull requests authored by the profile owner in
other accounts' repositories. It separates merged and open PRs, omits closed
unmerged PRs, and links each count to the matching GitHub list. New projects
appear automatically. The latest contribution is the most recently updated
open or merged PR for that project. Draft PRs count as open and are marked.

OpenRadioss (OpenCourant) is included in the same table. Its preserved contributions
are queried by author on OpenCourant's default branch, with a link to the latest
commit and full commit history. These commits are not counted as merged PRs:
the original PR objects may no longer be searchable after a repository migration.
A project found through both sources appears only once. The Upstream work column
links merged PRs or preserved commits, keeping the distinction visible.

Only the text between the `OPEN-SOURCE-WORK` markers is generated. The introduction
and contact details remain editable. API errors or an unexpectedly empty preserved
history stop the update, retaining the existing table for inspection.

The workflow uses its own `GITHUB_TOKEN`; no personal token or local computer is
needed. It only writes README.md. API errors, incomplete pagination or missing
markers stop the update and leave the previous README intact. GitHub search has
a 1,000-result limit; the updater stops instead of showing truncated totals if
that limit is exceeded.

The visible check date uses China time and changes once a day. This records that
the data was refreshed even when PR counts stay the same. Public repositories
without activity for 60 days can have scheduled workflows disabled by GitHub;
if that happens, enable the workflow again in Actions.

For a local preview, sign in with GitHub CLI and run:

```sh
python scripts/update_open_source.py --login lililii124
python -m unittest discover -s scripts -p 'test_*.py'
```
