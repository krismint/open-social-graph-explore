# Third-Party Notices

This file records third-party packages, assets, and platform-specific code paths used by OSGE.

The OSGE Non-Commercial Research License in `LICENSE` applies to original OSGE code unless a file or dependency states otherwise. Third-party packages and copied assets remain under their own licenses and terms.

## Python Dependencies

Direct runtime dependencies are listed in `requirements.txt`. License names below are based on installed package metadata and should be reviewed when dependencies are upgraded.

| Package | Role | License metadata |
| --- | --- | --- |
| Datasette | SQLite browsing and local data inspection support | Apache-2.0 |
| FastAPI | Local Web API framework | MIT |
| NetworkX | Graph analysis | BSD-3-Clause |
| pyvis | Graph visualization | BSD |
| httpx | HTTP client | BSD-3-Clause |
| Playwright | Browser/CDP automation | Apache-2.0 |
| PyExecJS | JavaScript runtime bridge for signing helpers | MIT |
| xhshow | Xiaohongshu signing helper | No license metadata in installed package |
| Uvicorn | ASGI server used by `scripts/osge_service.sh` | BSD-3-Clause |

Transitive dependencies are not exhaustively listed here. Maintainers should review package metadata before release builds or redistribution.

## Platform-Specific Assets

### `adapters/assets/douyin.js`

This file contains platform-specific signing code copied from an external repository referenced in the file header:

- ShilongLee/Crawler: https://github.com/ShilongLee/Crawler/tree/main
- Upstream license: Non-Commercial Use License 1.0 / 非商业使用许可证 1.0
- License file: https://github.com/ShilongLee/Crawler/blob/main/LICENSE

The file header states that the material is for learning and communication use and prohibits commercial and illegal use. This asset is not original OSGE code and is not relicensed by OSGE.

Before public release or redistribution, maintainers should confirm that redistribution is permitted by the upstream author, or replace/remove the asset if permission is unclear.

### MediaCrawler Reference

OSGE's platform adapter design and crawler boundary documentation have been reviewed against the non-commercial learning constraints used by MediaCrawler:

- NanmiCoder/MediaCrawler: https://github.com/NanmiCoder/MediaCrawler
- Upstream license: NON-COMMERCIAL LEARNING LICENSE 1.1 / 非商业学习使用许可证 1.1
- License file: https://github.com/NanmiCoder/MediaCrawler/blob/main/LICENSE

MediaCrawler code is not vendored as an OSGE runtime dependency unless a future file explicitly states otherwise. Any future copied code, derived implementation, or direct integration must keep the upstream attribution and license restrictions.

## Platform Terms

OSGE adapters interact with third-party platforms. OSGE does not grant permission to bypass platform access controls, rate limits, login requirements, anti-abuse systems, or terms of service.

Use only public, authorized, or user-owned data. See `docs/ETHICS.md` for project boundaries.
