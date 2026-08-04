## Renaming the repository broke PyPI trusted publishing — 20260804 12:40

Renaming `lucagattoni/Pinakes` → `lucagattoni/pinakes` was checked against everything inside the
repo — 64 URLs, the docs site, CI, the gates — and all of it passed. What it broke was outside the
repo: **PyPI's trusted publisher matches on the exact repository name**, and it is registered on
pypi.org, where no gate here can see it.

So `v0.9.0` tagged, built, smoke-tested, and was refused at the upload:

    invalid-publisher — valid token, but no corresponding publisher
    repository: "lucagattoni/pinakes"      # the token's claim, post-rename
                                           # the publisher still says "Pinakes"

**Nothing was uploaded**, which is the only reason this was recoverable: PyPI never allows
re-uploading a version, so had the rename landed *between* two files of the same upload the version
would have been burned and 0.9.0 would have had to be skipped. Verified against
`https://pypi.org/simple/pinakes/` rather than the JSON API, which is CDN-cached and has read as
"missing" for a correct upload before (20260729).

**The durable lesson: a rename's blast radius is every system that identifies this repo by name, and
most of them are not in the repo.** Before renaming, enumerate the external identifiers —
trusted-publishing publishers, deploy keys and webhooks, any CI in another repo that clones this
one, badge and package-index metadata — because a repo-wide grep proves only that the *inside* is
consistent. GitHub's redirect for the old URL is what makes the inside look fine and hides this.

Ordering that would have avoided the outage entirely: **update the external publisher first, then
rename, then tag.** The publisher can name a repository that does not exist yet, so there is no
window where neither name works — and the reverse order guarantees one.
