# Tasks

## 1. Registry

- [x] 1.1 Add `claimcoach/models/types.py` (`ModelRole`) and `claimcoach/models/registry.py` (`ModelSpec`, `ConversionSpec`, `ResidencyPolicy`, `AcquireCommands`, `ModelRegistry`, `models_home`, `ensure_registry_file`); verify `test_us_2_1_every_role_registered`, `test_us_2_1_ports_outside_range_rejected`
- [x] 1.2 Ship `claimcoach/models/models.default.yaml`; verify `test_us_2_1_default_file_written_once`
- [x] 1.3 Path rules; verify `test_us_2_1_paths_resolve_under_models_home` and the escaping-path cases

## 2. Operations

- [x] 2.1 `python -m claimcoach.models init|check`, Makefile `models-init`, `models-check`; verify the CLI tests and `make models-check`
- [x] 2.2 Move `pyyaml` to runtime dependencies; verify `make check`
- [x] 2.3 Record `evidence/US-2.1/test-report.md` and `junit.xml`
