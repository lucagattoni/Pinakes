`pnk doctor` on a KB with no index now says *"not built yet, so the link checks did not run"* rather
than only *"not built yet"*. Every index-backed check is produced from one place, so an absent index
silently removed them all — including link coverage, which is the check a reader consults after
authoring links. A report that stops listing a check reads as nothing to report about it.
