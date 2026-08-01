Four tests that build an unreadable directory now skip where the process bypasses directory
permissions (root, as in CI's container) instead of asserting against a precondition they could not
construct, and a test asserting `pathlib`'s exact "unacceptable pattern" wording now asserts the
property it meant. No shipped behaviour changes.
