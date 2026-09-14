# Evaluation answer key — INC-SYN-003 (synthetic)

**Not read by the server.**

Known cause: `ZMM_MATERIAL_UPLOAD` appends every processed row into
`IT_MATERIAL_BUFFER` and never clears or frees it during the loop. This
was invisible on the small files the job normally processes, but the
2026-09-11 run received an unusually large input file; the table grew
past the work process's heap/extended-memory limits at iteration
4,812,003 and the runtime terminated with TSV_TNEW_PAGE_ALLOC_FAILED. The
syslog's climbing memory-usage warnings in the minutes before the dump,
together with the dump's exact line number and internal table name, are
the two pieces of evidence that should be connected. A correct
investigation should distinguish this from a generic "out of memory"
verdict by naming the specific unbounded internal table and recommending
either periodic FREE/DELETE calls or processing the file in batches.
