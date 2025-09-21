# BugsDotJar-Dissection (Extended for HotBugs Metadata)

This repository is a fork of [BugsDotJar-Dissection](https://github.com/tdurieux/bugs-dot-jar-dissection), extended to generate metadata for [HotBugs.jar](https://github.com/carolhanna01/HotBugs-dot-jar) bugs.  

The exported metadata (`meta-data.json`) is used by the BugsDotJar benchmark and required by  
[Cerberus](<anonymous-cerberus-link>) to set up and run experiments.

This fork currently contains metadata for **67 bugs** generated from a subset of HotBugs.jar.

---

## Notes
- This repository is **not runnable on its own**.  
- It provides metadata only; repair experiments are conducted via the Cerberus fork.  
- Original project documentation is preserved in [bugs-dot-jar-dissection-readme.md](bugs-dot-jar-dissection-readme.md).
