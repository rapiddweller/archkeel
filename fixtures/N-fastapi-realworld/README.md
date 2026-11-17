# FastAPI architecture, checked at a pinned commit

This folder holds only ArchKeel's own files: the layering contract, the scan config and the
component graph. It holds no FastAPI source. `SOURCE.json` names the pin (repository, release,
commit, licence). The gallery fetches that exact commit when it builds and scans the package
`fastapi/` of it. The contract records the architecture as built at the pin: the components, the
import directions that the code shows, and one pair that must stay unrelated.
