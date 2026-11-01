# Tasks

## 1. Measure

- [x] 1.1 Add `tests/svg_layout.py` (styles, text boxes, containers, free text); verify `test_us_13_6_anchors_are_measured`
- [x] 1.2 Check every diagram's text against its container; verify `test_us_13_6_node_text_fits`, `test_us_13_6_labels_fit_chips`, `test_us_13_6_free_text_on_canvas`, `test_us_13_6_every_diagram_has_text`
- [x] 1.3 Name each overflow and fail closed; verify `test_us_13_6_overflow_is_named`, `test_us_13_6_free_text_off_canvas_is_named`, `test_us_13_6_vertical_padding_is_checked`, `test_us_13_6_unmeasurable_text_is_refused`, `test_us_13_6_orphan_container_is_named`

## 2. Evidence

- [x] 2.1 Record `evidence/US-13.6/test-report.md` and `junit.xml`; verify `make evidence-check`
