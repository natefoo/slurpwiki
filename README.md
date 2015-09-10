slurpwiki
=========

I wanted to make a copy of a wiki including its revision history from
SourceForge into a git repo. After looking through the Apache Allure code, it
didn't seem to be possible to:

- Clone or check out an Allure wiki
- Get raw versions of old revisions of pages
- Get commit metadata
- Do anything useful via its wiki API

So this script works around those missing features to extract a wiki and import
it to git.
