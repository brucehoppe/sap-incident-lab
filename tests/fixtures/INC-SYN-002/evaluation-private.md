# Evaluation answer key — INC-SYN-002 (synthetic)

**Not read by the server.**

Known cause: `ZMM_MATERIAL_REPROCESS` reads records in pages of 100 using
`:start_matnr` as the pagination cursor, but the variable is never advanced
to the last MATNR of the fetched page before the next SELECT. Every
iteration re-reads the same 100 rows starting at 000000000000100000
forever — steady CPU use, no database lock, no error, and no progress
through the material master. The job log's identical repeated lines and
the trace's "unchanged since previous SELECT" note are the two signals
that should be connected. A correct investigation should flag this as an
application-logic infinite loop (not a lock, not a performance problem)
and recommend inspecting the pagination logic in the custom program.
