# pipeline/filters/

Processing decision logic. Adapters adapt, pipeline decides.

## Files

- `item_filters.py` - Two-tier filtering (adapter vs processor level)

## Functions

| Function | Level | Purpose |
|----------|-------|---------|
| `should_skip_item()` | Adapter | Don't save at all (roll call, adjournment) |
| `should_skip_processing()` | Processor | Save but skip LLM (proclamations) |
| `should_skip_matter()` | Processor | Skip matter types (minutes, info items) |
| `is_public_comment_attachment()` | Processor | Skip bulk scanned PDFs |

## Migration

Moved from `vendors/utils/item_filters.py`. Old location re-exports with deprecation.
