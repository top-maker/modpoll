# Changelog

## [1.6.2](https://github.com/top-maker/modpoll/compare/v1.6.1...v1.6.2) (2026-10-28)


### Bug Fixes

* Codex/1x reliability gaps ([#111](https://github.com/top-maker/modpoll/issues/111)) ([83c76d9](https://github.com/top-maker/modpoll/commit/83c76d92b83b0a5f191d8f26f433903191597c22))
* correct polling limits and MQTT queue handling ([3d1c4f9](https://github.com/top-maker/modpoll/commit/3d1c4f9619678c926c7ce6b67a7e88c9b8888de1))
* harden polling correctness and release safety ([#109](https://github.com/top-maker/modpoll/issues/109)) ([9139956](https://github.com/top-maker/modpoll/commit/9139956481d47961cf8313cb46e579b136888013))
* preserve versioned documentation across stable releases ([#115](https://github.com/top-maker/modpoll/issues/115)) ([0866a43](https://github.com/top-maker/modpoll/commit/0866a43e00ffdbec96ab83b59e813eff413584b6))

## [1.6.1](https://github.com/top-maker/modpoll/compare/v1.6.0...v1.6.1) (2026-10-27)


### Bug Fixes

* Fail fast on Poetry lock drift and invalidate stale CI venv caches ([#107](https://github.com/top-maker/modpoll/issues/107)) ([e274c4a](https://github.com/top-maker/modpoll/commit/e274c4afaff286bee248b12e356b906c24c22b44))
* harden modpoll writes and polling reliability ([#108](https://github.com/top-maker/modpoll/issues/108)) ([6b6a49a](https://github.com/top-maker/modpoll/commit/6b6a49afd5c3cec6c522a1f70fa703c8bbc435f8))
* remove clean_session from MQTT v3.1.1 connect call ([#105](https://github.com/top-maker/modpoll/issues/105)) ([565e4c9](https://github.com/top-maker/modpoll/commit/565e4c9d58fd542c74a708952c7723bafdbbca1a))

## [1.6.0](https://github.com/top-maker/modpoll/compare/v1.5.1...v1.6.0) (2025-12-06)


### Features

* add bit-level access for boolean registers ([cecf79d](https://github.com/top-maker/modpoll/commit/cecf79d24de79fdda7f524516fb163f35f392e3f))
* add new argument 'serial' to support multiple framers, including rtu/ascii/binary. Keep the old 'rtu' argument as an alias to 'serial' argument for backward compatibility. ([d42ab78](https://github.com/top-maker/modpoll/commit/d42ab78801d16c96cde852686f77ec6694776cf9))
* add support for ascii framer ([#97](https://github.com/top-maker/modpoll/issues/97)) ([c918e74](https://github.com/top-maker/modpoll/commit/c918e74ca9e9c69c8fbf47712cb46300bf0630a9))
* upgrade to python 3.10 and pymodbus 3.9.0 ([189b3fd](https://github.com/top-maker/modpoll/commit/189b3fd71876e64e9ef6e81b5832508fb451a37c))


### Bug Fixes

* bit syntax is only used with bool dtype ([cf1e2b9](https://github.com/top-maker/modpoll/commit/cf1e2b9b732c5de1639549b06744251a9b7e746e))
* forward mqtt tls flags to handler ([#93](https://github.com/top-maker/modpoll/issues/93)) ([d31db25](https://github.com/top-maker/modpoll/commit/d31db252257cc4b8c1ddcd5b8cdca2c8072ca227))
* guard mqtt cleanup on setup errors ([#95](https://github.com/top-maker/modpoll/issues/95)) ([daa8c0c](https://github.com/top-maker/modpoll/commit/daa8c0c7d838468ba880397c5e38f98a3b0eb460))
* incompatibility issues due to pymodbus 3.9+ ([d59a336](https://github.com/top-maker/modpoll/commit/d59a336eb68758f2bd521158926a1c1c6171a995))
* Sphinx build errors ([2d06ee6](https://github.com/top-maker/modpoll/commit/2d06ee64ebda3303e9c8be9ebecdf0808c72b3f7))

## [1.5.1](https://github.com/top-maker/modpoll/compare/v1.5.0...v1.5.1) (2025-09-29)


### Bug Fixes

* Clear reference value when disconnect ([#90](https://github.com/top-maker/modpoll/issues/90)) ([9543ce0](https://github.com/top-maker/modpoll/commit/9543ce0407686fd1398fd2db2eaecc42192d08e0)), closes [#87](https://github.com/top-maker/modpoll/issues/87)
* Replace unreliable mqtt broker ([#88](https://github.com/top-maker/modpoll/issues/88)) ([bce269c](https://github.com/top-maker/modpoll/commit/bce269c3ce246ecf493b8a992c2f6e6293e7407e))

## [1.5.0](https://github.com/top-maker/modpoll/compare/v1.4.1...v1.5.0) (2025-03-13)


### Features

* Update docker compose to conform to new specification ([abc55aa](https://github.com/top-maker/modpoll/commit/abc55aa363d76dc35b6a9731e31ab4b551a7b435))


### Bug Fixes

* CI pipelines issue with wrong poetry version ([14d0563](https://github.com/top-maker/modpoll/commit/14d0563f0928b4dd0673290660bf56908090c836))
* Install specific version of plugins ([98af91c](https://github.com/top-maker/modpoll/commit/98af91c5dcf241754e05182e4865595ea9d5a381))
* Wrong poll size in docs ([4ad6dbf](https://github.com/top-maker/modpoll/commit/4ad6dbfeabeaa8f5e9fdbe7dfeb240c6eb6ecab1))


### Reverts

* Install poetry before cache check ([2041db7](https://github.com/top-maker/modpoll/commit/2041db7c3e583e3acb75bc3b7836db46efa2589d))


### Documentation

* Add description for polling string reference example ([3bb8ade](https://github.com/top-maker/modpoll/commit/3bb8adeb4ca09bed05bf87cb8271dc02bfc8a585))
* Update screenshots ([e44ac1a](https://github.com/top-maker/modpoll/commit/e44ac1a33cb3806a665103e1e304e909c1a2f73a))

## [1.4.1](https://github.com/top-maker/modpoll/compare/v1.4.0...v1.4.1) (2025-01-03)


### Bug Fixes

* Eastron meter config issue ([d58ed36](https://github.com/top-maker/modpoll/commit/d58ed36e1bc75be72e4d14ffbcf16f41f7958386))


### Documentation

* Add reference scale usage in examples ([8b4319c](https://github.com/top-maker/modpoll/commit/8b4319c014be71bb5ac121888cc7dd9b8f552765)), closes [#75](https://github.com/top-maker/modpoll/issues/75)

## [1.4.0](https://github.com/top-maker/modpoll/compare/v1.3.3...v1.4.0) (2024-11-15)


### Features

* Add example config for Eastron SDM120 ([#72](https://github.com/top-maker/modpoll/issues/72)) ([2dde6b9](https://github.com/top-maker/modpoll/commit/2dde6b9b413a1c7fba19ba88dc8f1e7df8287c25))
* Allow HEX number in configuration file ([#70](https://github.com/top-maker/modpoll/issues/70)) ([6324269](https://github.com/top-maker/modpoll/commit/63242699b75b5169abc8064c1546faa92a8754de))
* Publish MQTT message for each single reference. ([adb869f](https://github.com/top-maker/modpoll/commit/adb869faeb375ec92d1158bd87c0389de7eceb09))


### Bug Fixes

* Rename doc include config_template.csv ([#73](https://github.com/top-maker/modpoll/issues/73)) ([8003ff3](https://github.com/top-maker/modpoll/commit/8003ff33a42143766223f2b02307cd17409b4059))

## [1.3.3](https://github.com/top-maker/modpoll/compare/v1.3.2...v1.3.3) (2024-10-15)


### Bug Fixes

* CI docs pipeline issue ([ada4089](https://github.com/top-maker/modpoll/commit/ada4089df1bb3063641820274a2c476d4a421321))

## [1.3.2](https://github.com/top-maker/modpoll/compare/v1.3.1...v1.3.2) (2024-10-15)


### Bug Fixes

* CI pipeline issue ([9386455](https://github.com/top-maker/modpoll/commit/9386455652025ea300dfdef5034738fa8936a66e))

## [1.3.1](https://github.com/top-maker/modpoll/compare/v1.3.0...v1.3.1) (2024-10-14)


### Bug Fixes

* Arguments mqtt-qos doesn't work for publish ([0a65d0a](https://github.com/top-maker/modpoll/commit/0a65d0ad1efe5067c080f7dd02afc1a8cb3c8478))
* Zsh parse error due to the special character used in mqtt-publish-topic-pattern. ([98230e8](https://github.com/top-maker/modpoll/commit/98230e8e78c77e7a0334d101ac990f53e599ce1d))

## [1.3.0](https://github.com/top-maker/modpoll/compare/v1.2.0...v1.3.0) (2024-10-13)


### Features

* Optimize code to make it more object oriented ([7195e29](https://github.com/top-maker/modpoll/commit/7195e297b5e658b05bb1c7c75c2d02f2ab886331))
* Remove importlib-metadata dependency since we drop support for pre-python3.8 environments. ([36a6fd4](https://github.com/top-maker/modpoll/commit/36a6fd43e81512af819cd7e00cdef4385e56e7ca))
* Support running multiple master instances ([#64](https://github.com/top-maker/modpoll/issues/64)) ([c44b597](https://github.com/top-maker/modpoll/commit/c44b597f45a1c9fd8b3b49562d74f959d21cd1f0))


### Bug Fixes

* Adjust delay to every loop iteration ([e368922](https://github.com/top-maker/modpoll/commit/e368922b925bcdf602d42716d2a72631f1134639))
* Allow github action to read the PR title and add labels ([22cb7c8](https://github.com/top-maker/modpoll/commit/22cb7c8dce284675193865c8fe399320bb0f2636))

## [1.2.0](https://github.com/top-maker/modpoll/compare/v1.1.0...v1.2.0) (2024-08-25)


### Features

* Introduce MQTT topic pattern to replace the existing MQTT topic prefix. ([58d3f67](https://github.com/top-maker/modpoll/commit/58d3f6719b7c78b0c17cfb60ca7013e5f8d1bccb))
* Add docker compose for better developer experience. ([01f15e8](https://github.com/top-maker/modpoll/commit/01f15e8d140eadf3413471463fbb26cd7d8fc175))


### Bug Fixes

* Validate action issue ([f8ef12e](https://github.com/top-maker/modpoll/commit/f8ef12e018009ec1c8b4d554829156e93c9a5b98))
* Typos ([9349864](https://github.com/top-maker/modpoll/commit/9349864c5712fad3da9218d8f8b72529da5e03fa))


## [1.1.0](https://github.com/top-maker/modpoll/compare/1.0.0...v1.1.0) (2024-08-03)


### Features

* add docker run commands for dev ([074d51e](https://github.com/top-maker/modpoll/commit/074d51e6196ca342d71c103e55a9c9e72cd3462b))
* add test cases for pytest ([99fc461](https://github.com/top-maker/modpoll/commit/99fc4613034e8aac1a24a760bfe395467a554092))
* support paho v2 ([#52](https://github.com/top-maker/modpoll/issues/52)) ([3e6681a](https://github.com/top-maker/modpoll/commit/3e6681a56497672c664a200e95728d7202a1964f))


### Bug Fixes

* allow user defined docker registry ([38acfcc](https://github.com/top-maker/modpoll/commit/38acfcc16f8143fe91e716ff734d4e96e8cc9035))
* device list is not properly used ([1824bed](https://github.com/top-maker/modpoll/commit/1824bede7a4085cf31243a261a7e074ad506c453))
* duplications in ci actions ([db5c667](https://github.com/top-maker/modpoll/commit/db5c667138afa4d0226b77655a4abe179bce866a))
* paho v2 changes in callbacks ([09316f8](https://github.com/top-maker/modpoll/commit/09316f8e8c247148d22f1b56a60fd35d6072ab6f))
* poetry warning ([44ec61f](https://github.com/top-maker/modpoll/commit/44ec61fd159e89b630ded9674c0a535cd1ba1a60))
* Unexpected input for release-please ([24703fe](https://github.com/top-maker/modpoll/commit/24703fe098379016447ab50ab89276e0f0f734ef))


### Documentation

* update CHANGELOG.md ([73fcc01](https://github.com/top-maker/modpoll/commit/73fcc010cb0ddbf4a1aa149ac28a354cd1bc5c39))


## [1.0.0](https://github.com/top-maker/modpoll/compare/0.8.4...1.0.0) (2024-07-11)


### ⚠ BREAKING CHANGES

* Release v1.0.0

### Features

* Support Modbus RTU/TCP/UDP devices

* Poll data from multiple Modbus devices

* Publish data to MQTT broker for remote debugging

* Log data for further investigation

* Provide docker solution for continuous data polling in production
